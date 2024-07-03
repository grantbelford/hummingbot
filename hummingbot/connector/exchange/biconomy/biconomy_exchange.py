import asyncio
from decimal import Decimal
# import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.biconomy import (
    biconomy_constants as CONSTANTS,
    biconomy_utils,
    biconomy_web_utils as web_utils,
)
from hummingbot.connector.exchange.biconomy.biconomy_api_order_book_data_source import BiconomyAPIOrderBookDataSource
from hummingbot.connector.exchange.biconomy.biconomy_api_user_stream_data_source import BiconomyAPIUserStreamDataSource
from hummingbot.connector.exchange.biconomy.biconomy_auth import BiconomyAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import TradeFillOrderDetails, combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent, OrderFilledEvent
# from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class BiconomyExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0

    web_utils = web_utils

    def __init__(self,
                 client_config_map: "ClientConfigAdapter",
                 biconomy_api_key: str,
                 biconomy_api_secret: str,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN,
                 ):
        self.api_key = biconomy_api_key
        self.secret_key = biconomy_api_secret
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._last_trades_poll_biconomy_timestamp = 1.0
        self._orders: List[Dict] = []
        self._trades: List[Dict] = []
        super().__init__(client_config_map)

    @staticmethod
    def biconomy_order_type(order_type: OrderType) -> str:
        return order_type.name.upper()

    @staticmethod
    def to_hb_order_type(biconomy_type: str) -> OrderType:
        return OrderType[biconomy_type]

    @property
    def authenticator(self):
        return BiconomyAuth(
            api_key=self.api_key,
            secret_key=self.secret_key,
            time_provider=self._time_synchronizer)

    def domain_type(self):
        return "www" if self._domain == "biconomy" else "vip"

    @property
    def name(self) -> str:
        return "biconomy"

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID_PREFIX

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def check_network_request_path(self):
        return CONSTANTS.PING_PATH_URL

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.MARKET]

    async def get_all_pairs_prices(self) -> List[Dict[str, str]]:

        results = {}
        pairs_prices = await self._api_get(path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL)
        for pair_price_data in pairs_prices["tickers"]:
            results[pair_price_data["symbol"]] = {
                "best_bid": pair_price_data["buy"],
                "best_ask": pair_price_data["sell"],
            }
        return results

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        error_description = str(request_exception)
        is_time_synchronizer_related = ("-1021" in error_description
                                        and "Timestamp for this request" in error_description)
        return is_time_synchronizer_related

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        return str(CONSTANTS.ORDER_NOT_EXIST_ERROR_CODE) in str(
            status_update_exception
        ) and CONSTANTS.ORDER_NOT_EXIST_MESSAGE in str(status_update_exception)

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        return str(CONSTANTS.UNKNOWN_ORDER_ERROR_CODE) in str(
            cancelation_exception
        ) and CONSTANTS.UNKNOWN_ORDER_MESSAGE in str(cancelation_exception)

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
            domain=self._domain,
            auth=self._auth)

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return BiconomyAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
            api_factory=self._web_assistants_factory)

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return BiconomyAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self.domain,
        )

    def _get_fee(self,
                 base_currency: str,
                 quote_currency: str,
                 order_type: OrderType,
                 order_side: TradeType,
                 amount: Decimal,
                 price: Decimal = s_decimal_NaN,
                 is_maker: Optional[bool] = None) -> TradeFeeBase:
        is_maker = order_type is OrderType.LIMIT_MAKER
        return DeductedFromReturnsTradeFee(percent=self.estimate_fee_pct(is_maker))

    async def _place_order(self,
                           order_id: str,
                           trading_pair: str,
                           amount: Decimal,
                           trade_type: TradeType,
                           order_type: OrderType,
                           price: Decimal,
                           **kwargs) -> Tuple[str, float]:
        amount_str = str(f"{amount:f}")
        side_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        api_params = {
            "amount": amount_str,
            "market": symbol
        }
        if order_type is OrderType.LIMIT or order_type is OrderType.LIMIT_MAKER:
            price_str = price
            api_params["price"] = str(round(price_str, 5))
        api_params["side"] = side_str

        trade_types = "limit" if order_type is OrderType.LIMIT else "market"
        try:
            order_result = await self._api_post(
                path_url=CONSTANTS.TRADE_PATH_URL.format(f"{trade_types}"),
                data=api_params,
                limit_id=CONSTANTS.TRADE_PATH_URL,
                is_auth_required=True)
            o_id = str(order_result["result"]["id"])
            transact_time = order_result["result"]["ctime"] * 1e-3
        except IOError as e:
            error_description = str(e)
            is_server_overloaded = ("status is 503" in error_description
                                    and "Unknown error, please check your request or try again later." in error_description)
            if is_server_overloaded:
                o_id = "UNKNOWN"
                transact_time = self._time_synchronizer.time()
            else:
                raise
        return o_id, transact_time

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=tracked_order.trading_pair)
        o_id = await tracked_order.get_exchange_order_id()
        api_params = {
            "market": symbol,
            "order_id": int(o_id),
        }
        try:
            cancel_result = await self._api_post(
                path_url=CONSTANTS.CANCEL_ORDER_PATH_URL,
                data=api_params,
                is_auth_required=True)
            return True if "successful" or "Order not found" in cancel_result.get("message") else False
        except IOError as e:
            error_description = str(e)
            is_not_active = ("error" in error_description
                             and "Order not found" in error_description)
            if is_not_active:
                self.logger().debug(f"The order {order_id} does not exist on biconomy."
                                    f"No cancelation needed.")
                await self._order_tracker.process_order_not_found(order_id)
            else:
                raise

    async def _format_trading_rules(self, exchange_info_dict: list[dict]) -> List[TradingRule]:
        """
        Example:
        {
           "ticker":[
               {
                "buy":"0.378",
                "high":"0.39999995",
                "last":"0.388",
                "low":"0.374101",
                "sell":"0.387",
                "symbol":"BTC_USDT",
                "vol":"3485328.1114718"
            },
        }
        """
        trading_pair_rules = exchange_info_dict
        retval = []
        for rule in filter(biconomy_utils.is_exchange_information_valid, trading_pair_rules):
            try:
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=rule.get("symbol"))
                step_size = Decimal(str(10 ** rule.get("baseAssetPrecision")))

                retval.append(
                    TradingRule(trading_pair,
                                min_order_size=Decimal(0.0001),
                                min_price_increment=Decimal(0.0001),
                                min_base_amount_increment=Decimal(step_size),
                                min_notional_size=Decimal(0.0001)))

            except Exception:
                self.logger().exception(
                    f"Error parsing the trading pair rule {rule}. Skipping.")
        return retval

    async def _status_polling_loop_fetch_updates(self):
        await self._update_order_fills_from_trades()
        await super()._status_polling_loop_fetch_updates()

    async def _update_trading_fees(self):
        """
        Update fees information from the exchange
        """
        pass

    async def _user_stream_event_listener(self):
        """
        Listens to messages from _user_stream_tracker.user_stream queue.
        Traders, Orders, and Balance updates from the WS.
        """
        user_channels = [
            CONSTANTS.USER_ASSET_ENDPOINT_NAME,
            CONSTANTS.USER_ORDERS_ENDPOINT_NAME,
        ]
        async for event_message in self._iter_user_event_queue():
            try:
                channel: str = event_message.get("method", None)
                results: Dict[str, Any] = event_message.get("params", [])
                if "result" not in event_message and channel not in user_channels:
                    self.logger().error(
                        f"Unexpected message in user stream: {event_message}.", exc_info=True)
                    continue
                if channel == CONSTANTS.USER_ORDERS_ENDPOINT_NAME:
                    self._process_order_message(event_message)
                elif channel == CONSTANTS.USER_ASSET_ENDPOINT_NAME:
                    self._process_balance_message_ws(results)

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error(
                    "Unexpected error in user stream listener loop.", exc_info=True)
                await self._sleep(5.0)

    def _process_balance_message_ws(self, event_message):
        tokens_data: list[Dict[str, Any]] = event_message
        # Iterate over each token and its data
        for token_info in tokens_data:
            for token, info in token_info.items():
                if isinstance(info, dict):
                    asset_name = token
                    free_balance = Decimal(info.get("available", "0"))
                    locked_balance = Decimal(info.get("freeze", "0"))
                    total_balance = free_balance + locked_balance
                    self._account_available_balances[asset_name] = free_balance
                    self._account_balances[asset_name] = total_balance

    def _create_order_update_with_order_status_data(self, order_status: Dict[str, Any], order: InFlightOrder):
        state = ""
        execution_type = order_status["params"][0]
        deal_stock = int(order_status["params"][1]["deal_stock"])
        deal_money = int(order_status["params"][1]["deal_money"])
        if execution_type == 0 and deal_money == 0 and deal_stock == 0:
            state = "created"
        elif execution_type == 2 and deal_money > 0 and deal_stock > 0:
            state = "pending"
        elif execution_type == 3 and deal_stock > 0 and deal_money > 0:
            state = "finished"
        elif execution_type == 3 and deal_stock == 0 and deal_money == 0:
            state = "cancelled"
        order_update = OrderUpdate(
            trading_pair=order.trading_pair,
            update_timestamp=order_status["params"][1]["mtime"] * 1e-3,
            new_state=CONSTANTS.ORDER_STATE[state],
            client_order_id=order.client_order_id,
            exchange_order_id=str(order_status["params"][1]["id"]),
        )
        return order_update

    def _process_order_message(self, raw_msg: Dict[str, Any]):
        order_msg = raw_msg.get("params", {})
        client_order_id = str(order_msg[1].get("id", ""))
        tracked_order = self._order_tracker.all_updatable_orders_by_exchange_order_id.get(client_order_id)
        if not tracked_order:
            self.logger().debug(f"Ignoring order message with id {client_order_id}: not in in_flight_orders.")
            return

        order_update = self._create_order_update_with_order_status_data(order_status=raw_msg, order=tracked_order)
        self._order_tracker.process_order_update(order_update=order_update)

    async def _update_order_fills_from_trades(self):
        """
        This is intended to be a backup measure to get filled events with trade ID for orders,
        in case Biconomy's user stream events are not working.
        NOTE: It is not required to copy this functionality in other connectors.
        This is separated from _update_order_status which only updates the order status without producing filled
        events, since Biconomy's get order endpoint does not return trade IDs.
        The minimum poll interval for order status is 10 seconds.
        """
        small_interval_last_tick = self._last_poll_timestamp / \
            self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        small_interval_current_tick = self.current_timestamp / \
            self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        long_interval_last_tick = self._last_poll_timestamp / self.LONG_POLL_INTERVAL
        long_interval_current_tick = self.current_timestamp / self.LONG_POLL_INTERVAL

        if (long_interval_current_tick > long_interval_last_tick
                or (self.in_flight_orders and small_interval_current_tick > small_interval_last_tick)):
            self._last_trades_poll_biconomy_timestamp = self._time_synchronizer.time()
            order_by_exchange_id_map = {}
            for order in self._order_tracker.all_fillable_orders.values():
                order_by_exchange_id_map[order.exchange_order_id] = order

            tasks = []
            trading_pairs = self.trading_pairs
            for trading_pair in trading_pairs:
                await self._request_trades(trading_pair)
            tasks.extend(self._trades)

            if len(tasks) > 0:

                self.logger().debug(
                    f"Polling for order fills of {len(tasks)} trading pairs.")
                results = tasks

                for trade, trading_pair in zip(results, trading_pairs):
                    quote = trading_pair.split("-")[1]
                    exchange_order_id = str(trade["deal_order_id"])
                    if exchange_order_id in order_by_exchange_id_map:
                        # This is a fill for a tracked order
                        tracked_order = order_by_exchange_id_map[exchange_order_id]
                        fee = TradeFeeBase.new_spot_fee(
                            fee_schema=self.trade_fee_schema(),
                            trade_type=tracked_order.trade_type,
                            percent_token=quote,
                            flat_fees=[TokenAmount(amount=Decimal(
                                trade["fee"]), token=quote)]
                        )
                        trade_update = TradeUpdate(
                            trade_id=str(trade["id"]),
                            client_order_id=tracked_order.client_order_id,
                            exchange_order_id=exchange_order_id,
                            trading_pair=trading_pair,
                            fee=fee,
                            fill_base_amount=Decimal(trade["amount"]),
                            fill_quote_amount=Decimal(trade["amount"]),
                            fill_price=Decimal(trade["price"]),
                            fill_timestamp=trade["time"] * 1e-3,
                        )
                        self._order_tracker.process_trade_update(trade_update)
                    elif self.is_confirmed_new_order_filled_event(str(trade["id"]), exchange_order_id, trading_pair):
                        # This is a fill of an order registered in the DB but not tracked any more
                        self._current_trade_fills.add(TradeFillOrderDetails(
                            market=self.display_name,
                            exchange_trade_id=str(trade["id"]),
                            symbol=trading_pair))
                        self.trigger_event(
                            MarketEvent.OrderFilled,
                            OrderFilledEvent(
                                timestamp=float(trade["time"]) * 1e-3,
                                order_id=self._exchange_order_ids.get(
                                    str(trade["deal_order_id"]), None),
                                trading_pair=trading_pair,
                                # trade_type=TradeType.BUY if trade["isBuyer"] else TradeType.SELL,
                                order_type=OrderType.LIMIT_MAKER if trade["role"] == 1 else OrderType.LIMIT,
                                price=Decimal(trade["price"]),
                                amount=Decimal(trade["amount"]),
                                trade_fee=DeductedFromReturnsTradeFee(
                                    flat_fees=[
                                        TokenAmount(
                                            quote,
                                            Decimal(trade["fee"])
                                        )
                                    ]
                                ),
                                exchange_trade_id=str(trade["id"])
                            ))
                        self.logger().info(
                            f"Recreating missing trade in TradeFill: {trade}")

    async def _request_trades(self, trading_pair):
        order_ids = []
        await self._order_list(trading_pair)
        if len(self._orders) > 0:
            for order in self._orders:
                if order["state"] == "completed":
                    order_ids.append(order["id"])
            try:

                if len(order_ids) > 0:
                    trades_results = []
                    for order_id in order_ids:
                        params = {
                            "order_id": order_id,
                            "limit": "100",
                            "offset": "0",
                        }
                        trades = await self._api_post(
                            path_url=CONSTANTS.MY_TRADES_PATH_URL,
                            data=params,
                            is_auth_required=True,
                            limit_id=CONSTANTS.MY_TRADES_PATH_URL)
                        trades_results.append(trades)
                        if isinstance(trades, Exception):
                            self.logger().network(
                                f"Error fetching trades update for the order {trading_pair}: {trades}.",
                                app_warning_msg=f"Failed to fetch trade update for {trading_pair}."
                            )
                            continue

                    gathered_results = trades_results

                    for result in gathered_results:
                        if isinstance(result, Exception):
                            self.logger(f"Error in gathering trades: {str(result)}")
                        else:
                            self._trades.extend(result["result"]["records"])
            except IOError as e:
                error_description = str(e)
                self.logger(f"Failed to get trades: {error_description}")
                raise

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []

        if order.exchange_order_id is not None:
            exchange_order_id = int(order.exchange_order_id)
            trading_pair = await self.exchange_symbol_associated_to_pair(trading_pair=order.trading_pair)
            quote = trading_pair.split("_")[1]
            params = {
                "order_id": exchange_order_id,
                "offset": "0",
                "limit": "100",
            }
            all_fills_response = await self._api_post(
                path_url=CONSTANTS.MY_TRADES_PATH_URL,
                data=params,
                is_auth_required=True,
                limit_id=CONSTANTS.MY_TRADES_PATH_URL)

            for trade in all_fills_response["result"]["records"]:
                exchange_order_id = str(trade["deal_order_id"])
                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=order.trade_type,
                    percent_token=quote,
                    flat_fees=[TokenAmount(amount=Decimal(
                        trade["fee"]), token=quote)]
                )
                trade_update = TradeUpdate(
                    trade_id=str(trade["id"]),
                    client_order_id=order.client_order_id,
                    exchange_order_id=exchange_order_id,
                    trading_pair=trading_pair,
                    fee=fee,
                    fill_base_amount=Decimal(trade["amount"]),
                    fill_quote_amount=Decimal(trade["amount"]),
                    fill_price=Decimal(trade["price"]),
                    fill_timestamp=trade["time"] * 1e-3,
                )
                trade_updates.append(trade_update)
        return trade_updates

    async def _request_completed_orders(self, trading_pair):
        # query_time = int(self._last_trades_poll_biconomy_timestamp * 1e3)
        # self._last_trades_poll_biconomy_timestamp = self._time_synchronizer.time()
        try:
            params = {
                "api_key": self.api_key,
                "limit": "100",
                "market": trading_pair.replace("-", "_"),
                "offset": 0,
            }
            completed_orders = await self._api_post(
                path_url=CONSTANTS.ORDER_PATH_URL.format("finished"),
                data=params,
                is_auth_required=True,
                limit_id=CONSTANTS.ORDER_PATH_URL
            )
            result = completed_orders.get("result", {}).get("records", [])

            if len(result) > 0:
                for order in result:
                    deal_stock = float(order["deal_stock"])
                    deal_money = float(order["deal_money"])
                    if deal_stock > 0 and deal_money > 0:
                        order['state'] = "finished"
                    elif deal_stock == 0 and deal_money == 0:
                        order['state'] = "cancelled"
                self._orders.extend(result)  # Use extend instead of append to add orders correctly
            return result

        except IOError as e:
            error_description = str(e)
            self.logger(f"Failed to get Completed: {error_description}")
            raise

    async def _request_pending_orders(self, trading_pair):
        try:
            params = {
                "limit": "100",
                "market": trading_pair.replace("-", "_"),
                "offset": 0
            }
            pending_orders = await self._api_post(
                path_url=CONSTANTS.ORDER_PATH_URL.format("pending"),
                data=params,
                is_auth_required=True,
                limit_id=CONSTANTS.ORDER_PATH_URL
            )

            result = pending_orders.get("result", {}).get("records", [])

            if len(result) > 0:
                for order in result:
                    deal_stock = float(order["deal_stock"])
                    deal_money = float(order["deal_money"])
                    if deal_stock > 0 and deal_money > 0:
                        order['state'] = "pending"
                    elif deal_stock == 0 and deal_money == 0:
                        order['state'] = "created"
                    self._orders.extend(result)  # Use extend instead of append to add orders correctly

            return result

        except IOError as e:
            error_description = str(e)
            self.logger.error(f"Failed to get Pending Orders for {trading_pair}: {error_description}")
            raise

    async def _order_list(self, trading_pair):
        completed_orders_task = self._request_completed_orders(trading_pair)
        pending_orders_task = self._request_pending_orders(trading_pair)

        completed_orders, pending_orders = await asyncio.gather(completed_orders_task, pending_orders_task)

        self._orders.extend(completed_orders)
        self._orders.extend(pending_orders)

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        trading_pair = await self.exchange_symbol_associated_to_pair(trading_pair=tracked_order.trading_pair)
        order_id = tracked_order.exchange_order_id
        found_order_data = None

        # Fetch and list the orders
        await self._order_list(trading_pair)

        # Search for the specific order in the list of orders
        for order_data in self._orders:
            if order_data['id'] == order_id:
                found_order_data = order_data
                break

            state = order_data['state']
            if state in ["pending", "completed", "created"]:
                # Determine the state to fetch
                fetch_state = "pending" if state == "created" else state
                # Fetch updated order data
                data = await self._api_post(
                    path_url=CONSTANTS.ORDER_STATUS.format(fetch_state),
                    data={
                        "market": trading_pair,
                        "order_id": order_id},
                    is_auth_required=True,
                    limit_id=CONSTANTS.ORDER_STATUS
                )
                new_state = CONSTANTS.ORDER_STATE[state]
                timestamp = data["result"]["mtime"]
                return OrderUpdate(
                    client_order_id=tracked_order.client_order_id,
                    exchange_order_id=str(data["result"]["id"]),
                    trading_pair=tracked_order.trading_pair,
                    update_timestamp=timestamp * 1e-3,
                    new_state=new_state)
            else:
                new_state = CONSTANTS.ORDER_STATE[state]
                return OrderUpdate(
                    client_order_id=tracked_order.client_order_id,
                    exchange_order_id=tracked_order.exchange_order_id,
                    trading_pair=tracked_order.trading_pair,
                    update_timestamp=tracked_order.last_update_timestamp,
                    new_state=new_state)

        if not found_order_data:
            raise ValueError(f"Order {order_id} not found in fetched orders.")

    async def _update_balances(self):
        # Retrieve local asset names
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        # Fetch account information from the API
        account_info = await self._api_post(
            path_url=CONSTANTS.ACCOUNTS_PATH_URL,
            is_auth_required=True,
            limit_id=CONSTANTS.ACCOUNTS_PATH_URL
        )
        # Extract the token data
        tokens_data: Dict[str, Dict[str, Any]] = account_info.get('result', {})

        # Iterate over each token and its data
        for token, info in tokens_data.items():
            if isinstance(info, dict):
                asset_name = token
                free_balance = Decimal(info.get("available", "0"))
                locked_balance = Decimal(info.get("freeze", "0"))
                total_balance = Decimal(free_balance) + Decimal(locked_balance)
                self._account_available_balances[asset_name] = free_balance
                self._account_balances[asset_name] = total_balance
                remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: list[Dict]):
        mapping = bidict()

        for entry in filter(biconomy_utils.is_exchange_information_valid, exchange_info):
            base, quote = entry['symbol'].split('_')
            # Replace hyphens with empty strings and reassign to base or quote
            if "-" in base:
                base = base.replace("-", "")
            if "-" in quote:
                quote = quote.replace("-", "")
            mapping[entry["symbol"]] = combine_to_hb_trading_pair(
                base = base,
                quote = quote
            )
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        params = {
            "symbol": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        }

        resp_json = await self._api_request(
            method=RESTMethod.GET,
            path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL,
            params=params,
            limit_id=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL
        )
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        for pair_price_data in resp_json["ticker"]:
            if pair_price_data["symbol"] == symbol:
                # Extract the last traded price
                price = float(pair_price_data["last"])
                return price

        # If symbol not found, raise an exception or handle error
        raise ValueError(f"Symbol {symbol} not found in ticker data")