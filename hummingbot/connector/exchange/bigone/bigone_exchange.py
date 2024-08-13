import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.bigone import (
    bigone_constants as CONSTANTS,
    bigone_utils,
    bigone_web_utils as web_utils,
)
from hummingbot.connector.exchange.bigone.bigone_api_order_book_data_source import BigoneAPIOrderBookDataSource
from hummingbot.connector.exchange.bigone.bigone_api_user_stream_data_source import BigoneAPIUserStreamDataSource
from hummingbot.connector.exchange.bigone.bigone_auth import BigoneAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class BigoneExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0

    web_utils = web_utils

    def __init__(self,
                 client_config_map: "ClientConfigAdapter",
                 bigone_api_key: str,
                 bigone_api_secret: str,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN,
                 ):
        self.api_key = bigone_api_key
        self.secret_key = bigone_api_secret
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._last_trades_poll_bigone_timestamp = 1.0

        self._max_trade_id_by_symbol: Dict[str, int] = dict()
        super().__init__(client_config_map)

    @staticmethod
    def bigone_order_type(order_type: OrderType) -> str:
        return order_type.name.upper()

    @staticmethod
    def to_hb_order_type(bigone_type: str) -> OrderType:
        return OrderType[bigone_type]

    @property
    def authenticator(self):
        return BigoneAuth(
            api_key=self.api_key,
            secret_key=self.secret_key,
            time_provider=self._time_synchronizer)

    @property
    def name(self) -> str:
        return "bigone"

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

    async def _get_all_pairs_prices(self) -> Dict[str, Any]:
        results = {}
        pairs_prices = await self._api_get(path_url=CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL)
        for pair_price_data in pairs_prices:
            results[pair_price_data["data"]["asset_pair_name"]] = {
                "best_bid": pair_price_data["data"]["bid"],
                "best_ask": pair_price_data["data"]["ask"],
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
        return BigoneAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
            api_factory=self._web_assistants_factory)

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return BigoneAPIUserStreamDataSource(
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
        order_result = None
        amount_str = f"{amount:f}"
        type_str = BigoneExchange.bigone_order_type(order_type)
        side_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        api_params = {"asset_pair_name": symbol,
                      "side": side_str,
                      "amount": amount_str,
                      "type": type_str,
                      "client_order_id": order_id}
        if order_type is OrderType.LIMIT or order_type is OrderType.LIMIT_MAKER:
            price_str = f"{price:f}"
            api_params["price"] = price_str
            api_params["post_only"] = True

        try:
            order_result = await self._api_post(
                path_url=CONSTANTS.ORDER_PATH_URL,
                data=api_params,
                is_auth_required=True)
            o_id = str(order_result["data"]["id"])
            transact_time = bigone_utils.datetime_val_or_now(order_result["data"]["updated_at"], on_error_return_now=True).timestamp()
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
        api_params = {
            "client_order_id": order_id,
        }
        cancel_result = await self._api_post(
            path_url=CONSTANTS.CANCEL_ORDER_BY_ID_OR_CLIENT,
            data=api_params,
            is_auth_required=True)
        return True if cancel_result["data"].get("state") == "CANCELLED" else False

    async def _format_trading_rules(self, exchange_info_dict: list[Dict[str, Any]]) -> List[TradingRule]:
        """
        Example:
        {
            "id": "d2185614-50c3-4588-b146-b8afe7534da6",
            "quote_scale": 8,
            "quote_asset": {
                "id": "0df9c3c3-255a-46d7-ab82-dedae169fba9",
                "symbol": "BTC",
                "name": "Bitcoin"
            },
            "name": "BTG-BTC",
            "base_scale": 4,
            "min_quote_value":"0.001",
            "base_asset": {
                "id": "5df3b155-80f5-4f5a-87f6-a92950f0d0ff",
                "symbol": "BTG",
                "name": "Bitcoin Gold"
            }
        }
        """
        trading_pair_rules = exchange_info_dict["data"]
        retval = []
        for rule in filter(bigone_utils.is_exchange_information_valid, trading_pair_rules):
            try:
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=rule.get("name"))
                min_order_size = Decimal(rule.get("base_scale"))
                min_price_inc = Decimal(f"1e-{rule['quote_scale']}")
                min_amount_inc = Decimal(rule.get('min_quote_value'))

                retval.append(
                    TradingRule(trading_pair,
                                min_order_size=min_order_size,
                                min_price_increment=min_price_inc,
                                min_base_amount_increment=min_amount_inc))

            except Exception:
                self.logger().exception(f"Error parsing the trading pair rule {rule}. Skipping.")
        return retval

    async def _status_polling_loop_fetch_updates(self):
        await self._update_orders_fills(InFlightOrder)
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
            CONSTANTS.USER_TRADES_ENDPOINT_NAME,
            CONSTANTS.USER_ORDERS_ENDPOINT_NAME,
            CONSTANTS.USER_BALANCE_ENDPOINT_NAME,
        ]
        async for event_message in self._iter_user_event_queue():
            try:
                if "error" in event_message:
                    self.logger().error(
                        f"Unexpected message in user stream: {event_message}.", exc_info=True)
                    continue

                results: Dict[str, Any] = event_message
                for channel in user_channels:
                    if channel in event_message:
                        if channel == CONSTANTS.USER_TRADES_ENDPOINT_NAME:
                            self._process_trade_message(results[channel])
                        elif channel == CONSTANTS.USER_ORDERS_ENDPOINT_NAME:
                            self._process_order_message(results[channel])
                        elif channel == CONSTANTS.USER_BALANCE_ENDPOINT_NAME:
                            self._process_balance_message_ws(results[channel])
                        break

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error(
                    "Unexpected error in user stream listener loop.", exc_info=True)
                await self._sleep(5.0)

    def _process_balance_message_ws(self, account):
        asset_name = account["account"]["asset"]
        self._account_available_balances[asset_name] = Decimal(account["account"]["balance"]) - Decimal(account["account"]["lockedBalance"])
        self._account_balances[asset_name] = Decimal(str(account["account"]["balance"]))

    def _create_trade_update_with_order_fill_data(
            self,
            order_fill: Dict[str, Any],
            order: InFlightOrder):
        token = order_fill['trade']["market"].split("-")[1]
        fee = TradeFeeBase.new_spot_fee(
            fee_schema=self.trade_fee_schema(),
            trade_type=order.trade_type,
            percent_token=token,
            flat_fees=[TokenAmount(
                amount=Decimal(order_fill['trade']["takerOrder"]["filledFees"]),
                token=token
            )]
        )
        trade_update = TradeUpdate(
            trade_id=str(order_fill['trade']["id"]),
            client_order_id=order.client_order_id,
            exchange_order_id=order.exchange_order_id,
            trading_pair=order.trading_pair,
            fee=fee,
            fill_base_amount=Decimal(order_fill['trade']["amount"]),
            fill_quote_amount =Decimal(order_fill['trade']["takerOrder"]["filledAmount"]) * Decimal((order_fill['trade']["takerOrder"]["price"])),
            fill_price=Decimal(order_fill['trade']["takerOrder"]["price"]),
            fill_timestamp=bigone_utils.datetime_val_or_now(order_fill['trade']["takerOrder"]["createdAt"], on_error_return_now=True).timestamp(),
        )
        return trade_update

    def _process_trade_message(self, trade: Dict[str, Any], client_order_id: Optional[str] = None):
        if trade['trade']['takerOrder']["id"] != '':
            client_order_id = client_order_id or str(trade['trade']['takerOrder']["clientOrderId"])
            tracked_order = self._order_tracker.all_fillable_orders.get(client_order_id)
            if tracked_order is None:
                self.logger().debug(f"Ignoring trade message with id {client_order_id}: not in in_flight_orders.")
            else:
                trade_update = self._create_trade_update_with_order_fill_data(
                    order_fill = trade,
                    order = tracked_order)
                self._order_tracker.process_trade_update(trade_update)

    def _create_order_update_with_order_status_data(self, order_status: Dict[str, Any], order: InFlightOrder):
        order_update = OrderUpdate(
            trading_pair=order.trading_pair,
            update_timestamp=bigone_utils.datetime_val_or_now(order_status['order']["updatedAt"], on_error_return_now=True).timestamp(),
            new_state=CONSTANTS.ORDER_STATE[order_status['order']["state"]],
            client_order_id=order.client_order_id,
            exchange_order_id=str(order_status['order']["id"]),
        )
        return order_update

    def _process_order_message(self, raw_msg: Dict[str, Any]):
        order_msg = raw_msg.get("order", {})
        client_order_id = str(order_msg.get("clientOrderId", ""))
        tracked_order = self._order_tracker.all_fillable_orders.get(client_order_id)
        if not tracked_order:
            self.logger().debug(f"Ignoring order message with id {client_order_id}: not in in_flight_orders.")
            return

        order_update = self._create_order_update_with_order_status_data(order_status=raw_msg, order=tracked_order)
        self._order_tracker.process_order_update(order_update=order_update)

    # async def _update_order_fills_from_trades(self):
    #     """
    #     This is intended to be a backup measure to get filled events with trade ID for orders,
    #     in case Bigone's user stream events are not working.
    #     NOTE: It is not required to copy this functionality in other connectors.
    #     This is separated from _update_order_status which only updates the order status without producing filled
    #     events, since Bigone's get order endpoint does not return trade IDs.
    #     The minimum poll interval for order status is 10 seconds.
    #     """
    #     small_interval_last_tick = self._last_poll_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
    #     small_interval_current_tick = self.current_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
    #     long_interval_last_tick = self._last_poll_timestamp / self.LONG_POLL_INTERVAL
    #     long_interval_current_tick = self.current_timestamp / self.LONG_POLL_INTERVAL

    #     if (long_interval_current_tick > long_interval_last_tick
    #             or (self.in_flight_orders and small_interval_current_tick > small_interval_last_tick)):
    #         order_by_exchange_id_map = {}
    #         for order in self._order_tracker.all_fillable_orders.values():
    #             order_by_exchange_id_map[order.exchange_order_id] = order

    #         tasks = []
    #         trading_pairs = self.trading_pairs
    #         for trading_pair in trading_pairs:
    #             params = {
    #                 "asset_pair_name": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair),
    #                 "limit": "200"
    #             }
    #             tasks.append(self._api_get(
    #                 path_url=CONSTANTS.MY_TRADES_PATH_URL,
    #                 params=params,
    #                 is_auth_required=True))

    #         self.logger().debug(f"Polling for order fills of {len(tasks)} trading pairs.")
    #         results = await safe_gather(*tasks, return_exceptions=True)
    #         if len(results["data"]) > 0:
    #             for trades, trading_pair in zip(results["data"], trading_pairs):

    #                 if isinstance(trades, Exception):
    #                     self.logger().network(
    #                         f"Error fetching trades update for the order {trading_pair}: {trades}.",
    #                         app_warning_msg=f"Failed to fetch trade update for {trading_pair}."
    #                     )
    #                     continue
    #                 for trade in trades:
    #                     exchange_order_id = str(trade["orderId"])
    #                     token = trade["asset_pair_name"].split("-")[1],
    #                     if exchange_order_id in order_by_exchange_id_map:
    #                         # This is a fill for a tracked order
    #                         fees = trade["maker_fee"] if OrderType.LIMIT else trade["taker_fee"]
    #                         tracked_order = order_by_exchange_id_map[exchange_order_id]
    #                         fee = TradeFeeBase.new_spot_fee(
    #                             fee_schema=self.trade_fee_schema(),
    #                             trade_type=tracked_order.trade_type,
    #                             percent_token=token,
    #                             flat_fees=[TokenAmount(amount=Decimal(fees), token=token)]
    #                         )
    #                         trade_update = TradeUpdate(
    #                             trade_id=str(trade["id"]),
    #                             client_order_id=tracked_order.client_order_id,
    #                             exchange_order_id=exchange_order_id,
    #                             trading_pair=trading_pair,
    #                             fee=fee,
    #                             fill_base_amount=Decimal(trade["amount"]),
    #                             fill_quote_amount=Decimal(trade["amount"]),
    #                             fill_price=Decimal(trade["price"]),
    #                             fill_timestamp=trade["inserted_at"] * 1e-3,
    #                         )
    #                         self._order_tracker.process_trade_update(trade_update)
    #                     elif self.is_confirmed_new_order_filled_event(str(trade["id"]), exchange_order_id, trading_pair):
    #                         # This is a fill of an order registered in the DB but not tracked any more
    #                         self._current_trade_fills.add(TradeFillOrderDetails(
    #                             market=self.display_name,
    #                             exchange_trade_id=str(trade["id"]),
    #                             symbol=trading_pair))
    #                         fee = trade["maker_fee"] if OrderType.LIMIT else trade["taker_fee"]
    #                         self.trigger_event(
    #                             MarketEvent.OrderFilled,
    #                             OrderFilledEvent(
    #                                 timestamp=float(trade["time"]) * 1e-3,
    #                                 order_id=self._exchange_order_ids.get(str(trade["orderId"]), None),
    #                                 trading_pair=trading_pair,
    #                                 trade_type=TradeType.BUY if trade["side"] == "BID" else TradeType.SELL,
    #                                 order_type=OrderType.LIMIT_MAKER if trade["taker_fee"] is None else OrderType.LIMIT,
    #                                 price=Decimal(trade["price"]),
    #                                 amount=Decimal(trade["amount"]),
    #                                 trade_fee=DeductedFromReturnsTradeFee(
    #                                     flat_fees=[
    #                                         TokenAmount(
    #                                             token,
    #                                             Decimal(fee)
    #                                         )
    #                                     ]
    #                                 ),
    #                                 exchange_trade_id=str(trade["id"])
    #                             ))
    #                         self.logger().info(f"Recreating missing trade in TradeFill: {trade}")

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        # We have overridden `_update_orders_fills` to utilize batch trade updates to reduce API limit consumption.
        # See implementation in `_request_batch_order_fills(...)` function.
        pass

    async def _update_orders_fills(self, orders: List[InFlightOrder]):
        if orders:
            # Since we are keeping the last trade id referenced to improve the query performance
            # it is necessary to evaluate updates for all possible fillable orders every time (to avoid loosing updates)
            candidate_orders = list(self._order_tracker.all_fillable_orders.values())
            try:
                if candidate_orders:
                    trade_updates = await self._all_trade_updates_for_orders(candidate_orders)
                    for trade_update in trade_updates:
                        self._order_tracker.process_trade_update(trade_update)
            except asyncio.CancelledError:
                raise
            except Exception as request_error:
                order_ids = [order.client_order_id for order in candidate_orders]
                self.logger().warning(f"Failed to fetch trade updates for orders {order_ids}. Error: {request_error}")

    async def _all_trade_updates_for_orders(self, orders: List[InFlightOrder]) -> List[TradeUpdate]:
        # This endpoint is the only one on v2 for some reason
        symbols = {await self.exchange_symbol_associated_to_pair(trading_pair=o.trading_pair) for o in orders}
        trade_updates = []
        orders_to_process = {order.exchange_order_id: order for order in orders}
        for symbol in symbols:
            for _ in range(2):
                params = {"asset_pair_name": symbol, "limit": 200}
                if symbol in self._max_trade_id_by_symbol:
                    params["page_token"] = self._max_trade_id_by_symbol[symbol]
                result = await self._api_get(
                    path_url=CONSTANTS.MY_TRADES_PATH_URL,
                    params=params,
                    is_auth_required=True,
                )
                if len(result["data"]) > 0:
                    for trade_data in result["data"]:
                        order_ids = []
                        if trade_data["maker_order_id"] is not None:
                            order_ids.append(trade_data["maker_order_id"])
                        if trade_data["taker_order_id"] is not None:
                            order_ids.append(trade_data["taker_order_id"])
                        for order_id in order_ids:
                            if str(order_id) in orders_to_process:
                                order = orders_to_process[str(order_id)]
                                trade_fee = trade_data["maker_fee"]
                                fees = trade_data["maker_fee"] if trade_fee else trade_data["taker_fee"]

                                fee_token = trade_data["asset_pair_name"].split("-")[1]  # typo in the json by the exchange
                                fee = TradeFeeBase.new_spot_fee(
                                    fee_schema=bigone_utils.DEFAULT_FEES,
                                    trade_type=order.trade_type,
                                    percent_token=fee_token,
                                    flat_fees=[TokenAmount(amount=Decimal(fees), token=fee_token)],
                                )
                                trade_update = TradeUpdate(
                                    trade_id=str(trade_data["id"]),
                                    client_order_id=order.client_order_id,
                                    exchange_order_id=str(order_id),
                                    trading_pair=order.trading_pair,
                                    fee=fee,
                                    fill_base_amount=Decimal(trade_data["amount"]),
                                    fill_quote_amount=Decimal(trade_data["amount"]) * Decimal(trade_data["price"]),
                                    fill_price=Decimal(trade_data["price"]),
                                    fill_timestamp=bigone_utils.datetime_val_or_now(trade_data["inserted_at"], on_error_return_now=True).timestamp())
                                trade_updates.append(trade_update)
                    if len(result["data"]) > 0:
                        self._max_trade_id_by_symbol[symbol] = result["page_token"]
                    if len(result["data"]) < 1000:
                        break

        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        updated_order_data = await self._api_get(
            path_url = CONSTANTS.ORDER_BY_ID_OR_CLIENT,
            params = {
                "client_order_id": tracked_order.client_order_id},
            is_auth_required = True)

        new_state = CONSTANTS.ORDER_STATE[updated_order_data["data"]["state"]]

        order_update = OrderUpdate(
            client_order_id = tracked_order.client_order_id,
            exchange_order_id = str(updated_order_data["data"]["id"]),
            trading_pair = tracked_order.trading_pair,
            update_timestamp = bigone_utils.datetime_val_or_now(updated_order_data["data"]["updated_at"], on_error_return_now=True).timestamp(),
            new_state = new_state,
        )

        return order_update

    async def _update_balances(self):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        account_info: list[Dict[str, Any]] = await self._api_get(
            path_url = CONSTANTS.ACCOUNTS_PATH_URL,
            is_auth_required = True)

        balances = account_info
        for balance_entry in balances["data"]:
            asset_name = balance_entry["asset_symbol"]
            free_balance = Decimal(balance_entry["balance"]) - Decimal(balance_entry["locked_balance"])
            total_balance = Decimal(balance_entry["balance"])
            self._account_available_balances[asset_name] = free_balance
            self._account_balances[asset_name] = total_balance
            remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)
        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    async def _market_data_for_all_product_types(self) -> List[Dict[str, Any]]:
        all_exchange_info = []

        # For USDC collateralized products we need to change the quote asset from USD to USDC, to avoid colitions
        # in the trading pairs with markets for product type DMCBL
        exchange_info = await self._api_get(
            path_url = self.trading_pairs_request_path,
        )
        markets = exchange_info["data"]
        for market_info in markets:
            all_exchange_info.append(market_info)

        return all_exchange_info

    async def _initialize_trading_pair_symbol_map(self):
        try:
            all_exchange_info = await self._market_data_for_all_product_types()
            self._initialize_trading_pair_symbols_from_exchange_info(exchange_info=all_exchange_info)
        except Exception:
            self.logger().exception("There was an error requesting exchange info.")

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_data in filter(bigone_utils.is_exchange_information_valid, exchange_info):
            mapping[symbol_data["name"]] = combine_to_hb_trading_pair(base=symbol_data["base_asset"]["symbol"],
                                                                      quote=symbol_data["quote_asset"]["symbol"])
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        resp_json = await self._api_request(
            method = RESTMethod.GET,
            path_url = CONSTANTS.TICKER_BOOK_PATH_URL.format(symbol),
            limit_id=CONSTANTS.TICKER_BOOK_PATH_URL
        )

        return float(resp_json["close"])
