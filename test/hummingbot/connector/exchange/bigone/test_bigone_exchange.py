import asyncio
import json
import re
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

from aioresponses import aioresponses
from aioresponses.core import RequestCall

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.bigone import bigone_constants as CONSTANTS, bigone_web_utils as web_utils
from hummingbot.connector.exchange.bigone.bigone_exchange import BigoneExchange
from hummingbot.connector.test_support.exchange_connector_test import AbstractExchangeConnectorTests
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import get_new_client_order_id
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.event.events import MarketOrderFailureEvent


class BigoneExchangeTests(AbstractExchangeConnectorTests.ExchangeConnectorTests):

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()

    @property
    def all_symbols_url(self):
        return web_utils.public_rest_url(path_url=CONSTANTS.EXCHANGE_INFO_PATH_URL, domain=self.exchange._domain)

    @property
    def latest_prices_url(self):
        url = web_utils.public_rest_url(path_url=CONSTANTS.TICKER_BOOK_PATH_URL, domain=self.exchange._domain)
        url = url.format(self.exchange_trading_pair)
        return url

    @property
    def network_status_url(self):
        url = web_utils.private_rest_url(CONSTANTS.PING_PATH_URL, domain=self.exchange._domain)
        return url

    @property
    def trading_rules_url(self):
        return web_utils.public_rest_url(path_url=CONSTANTS.EXCHANGE_INFO_PATH_URL, domain=self.exchange._domain)

    @property
    def order_creation_url(self):
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL, domain=self.exchange._domain)
        return url

    @property
    def balance_url(self):
        url = web_utils.private_rest_url(CONSTANTS.ACCOUNTS_PATH_URL, domain=self.exchange._domain)
        return url

    @property
    def all_symbols_request_mock_response(self):
        return {
            "data": [
                {
                    "id": "d2185614-50c3-4588-b146-b8afe7534da6",
                    "quote_scale": 8,
                    "quote_asset": {
                        "id": "0df9c3c3-255a-46d7-ab82-dedae169fba9",
                        "symbol": self.quote_asset,
                        "name": "Bitcoin"
                    },
                    "name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "base_scale": 4,
                    "min_quote_value": "0.001",
                    "base_asset": {
                        "id": "5df3b155-80f5-4f5a-87f6-a92950f0d0ff",
                        "symbol": self.base_asset,
                        "name": "Bitcoin Gold"
                    }
                }
            ]
        }

    @property
    def latest_prices_request_mock_response(self):
        return {
            "volume": "190.4925000000000000",
            "open": "0.0777371200000000",
            "asset_pair_name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
            "low": "0.0742925600000000",
            "high": "0.0789150000000000",
            "daily_change": "-0.00029",
            "close": str(self.expected_latest_price),
            "bid": {
                "price": "0.0764777900000000",
                "order_count": 4,
                "quantity": "6.4248000000000000"
            },
            "ask": {
                "price": "0.0774425600000000",
                "order_count": 2,
                "quantity": "1.1741000000000000"
            }
        }

    @property
    def all_symbols_including_invalid_pair_mock_response(self) -> Tuple[str, Any]:
        response = {
            "data": [
                {
                    "id": "d2185614-50c3-4588-b146-b8afe7534da6",
                    "quote_scale": 8,
                    "quote_asset": {
                        "id": "0df9c3c3-255a-46d7-ab82-dedae169fba9",
                        "symbol": self.quote_asset,
                        "name": "Bitcoin"
                    },
                    "name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "base_scale": 4,
                    "min_quote_value": "0.001",
                    "base_asset": {
                        "id": "5df3b155-80f5-4f5a-87f6-a92950f0d0ff",
                        "symbol": self.base_asset,
                        "name": "Bitcoin Gold"
                    }
                },
                {
                    "id": "d2185614-50c3-4588-b146-b8afe7534da6",
                    "quote_scale": 8,
                    "quote_asset": {
                        "id": "0df9c3c3-255a-46d7-ab82-dedae169fba9",
                        "symbol": self.quote_asset,
                        "name": "Bitcoin"
                    },
                    "invalid": self.exchange_symbol_for_tokens("INVALID", "PAIR"),
                    "base_scale": 4,
                    "min_quote_value": "0.001",
                    "base_asset": {
                        "id": "5df3b155-80f5-4f5a-87f6-a92950f0d0ff",
                        "symbol": self.base_asset,
                        "name": "Bitcoin Gold"
                    }
                }
            ]
        }

        return "INVALID-PAIR", response

    @property
    def network_status_request_successful_mock_response(self):
        return {}

    @property
    def trading_rules_request_mock_response(self):
        return {
            "data": [
                {
                    "id": "d2185614-50c3-4588-b146-b8afe7534da6",
                    "quote_scale": 8,
                    "quote_asset": {
                        "id": "0df9c3c3-255a-46d7-ab82-dedae169fba9",
                        "symbol": self.quote_asset,
                        "name": "Bitcoin"
                    },
                    "name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "base_scale": 4,
                    "min_quote_value": "0.001",
                    "base_asset": {
                        "id": "5df3b155-80f5-4f5a-87f6-a92950f0d0ff",
                        "symbol": self.base_asset,
                        "name": "Bitcoin Gold"
                    }
                }
            ]
        }

    @property
    def trading_rules_request_erroneous_mock_response(self):
        return {
            "data": [
                {
                    "id": "d2185614-50c3-4588-b146-b8afe7534da6",
                    "quote_asset": {
                        "id": "0df9c3c3-255a-46d7-ab82-dedae169fba9",
                        "symbol": self.quote_asset,
                        "name": "Bitcoin"
                    },
                    "name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "base_asset": {
                        "id": "5df3b155-80f5-4f5a-87f6-a92950f0d0ff",
                        "symbol": self.base_asset,
                        "name": "Bitcoin Gold"
                    }
                }
            ]
        }

    @property
    def order_creation_request_successful_mock_response(self):
        return {
            "data":
                {
                    "id": self.expected_exchange_order_id,
                    "asset_pair_name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "price": "10.00",
                    "amount": "10.00",
                    "filled_amount": "9.0",
                    "avg_deal_price": "12.0",
                    "side": "ASK",
                    "state": "FILLED",
                    "type": "STOP_LIMIT",
                    "stop_price": "9.8",
                    "operator": "LTE",
                    "immediate_or_cancel": False,
                    "post_only": True,
                    "client_order_id": "",
                    "created_at": "2019-01-29T06:05:56Z",
                    "updated_at": "2019-01-29T06:05:56Z"
                }
        }

    @property
    def balance_request_mock_response_for_base_and_quote(self):
        return {
            "data": [
                {
                    "asset_symbol": self.base_asset,
                    "balance": "15",
                    "locked_balance": "5.0"
                },
                {
                    "asset_symbol": self.quote_asset,
                    "balance": "2000",
                    "locked_balance": "0.00000000"
                }

            ]
        }

    @property
    def balance_request_mock_response_only_base(self):
        return {
            "data": [
                {
                    "asset_symbol": self.base_asset,
                    "balance": "15",
                    "locked_balance": "5.0"
                }
            ]
        }

    @property
    def balance_event_websocket_update(self):
        return {
            "requestId": "1",
            "accountUpdate":
                {
                    "account": {
                        "asset": self.base_asset,
                        "balance": "15",
                        "lockedBalance": "5"
                    }
                }
        }

    @property
    def expected_latest_price(self):
        return 9999.9

    @property
    def expected_supported_order_types(self):
        return [OrderType.LIMIT, OrderType.MARKET]

    @property
    def expected_trading_rule(self):
        return TradingRule(
            trading_pair=self.trading_pair,
            min_order_size=Decimal(self.trading_rules_request_mock_response["data"][0]["base_scale"]),
            min_price_increment=Decimal(f'1e-{self.trading_rules_request_mock_response["data"][0]["quote_scale"]}'),
            min_base_amount_increment=Decimal(
                self.trading_rules_request_mock_response["data"][0]["min_quote_value"])
        )

    @property
    def expected_logged_error_for_erroneous_trading_rule(self):
        erroneous_rule = self.trading_rules_request_erroneous_mock_response["data"][0]
        return f"Error parsing the trading pair rule {erroneous_rule}. Skipping."

    @property
    def expected_exchange_order_id(self):
        return 28

    @property
    def is_order_fill_http_update_included_in_status_update(self) -> bool:
        return True

    @property
    def is_order_fill_http_update_executed_during_websocket_order_event_processing(self) -> bool:
        return False

    @property
    def expected_partial_fill_price(self) -> Decimal:
        return Decimal(10500)

    @property
    def expected_partial_fill_amount(self) -> Decimal:
        return Decimal("0.5")

    @property
    def expected_fill_fee(self) -> TradeFeeBase:
        return DeductedFromReturnsTradeFee(
            percent_token=self.quote_asset,
            flat_fees=[TokenAmount(token=self.quote_asset, amount=Decimal("30"))])

    @property
    def expected_fill_trade_id(self) -> str:
        return str(30000)

    def exchange_symbol_for_tokens(self, base_token: str, quote_token: str) -> str:
        return f"{base_token}-{quote_token}"

    def create_exchange_instance(self):
        client_config_map = ClientConfigAdapter(ClientConfigMap())
        return BigoneExchange(
            client_config_map=client_config_map,
            bigone_api_key="testAPIKey",
            bigone_api_secret="testSecret",
            trading_pairs=[self.trading_pair],
        )

    def validate_auth_credentials_present(self, request_call: RequestCall):
        self._validate_auth_credentials_taking_parameters_from_argument(
            request_call_tuple=request_call,
            params=request_call.kwargs["params"] or request_call.kwargs["data"]
        )

    def validate_order_creation_request(self, order: InFlightOrder, request_call: RequestCall):
        request_data = json.loads(request_call.kwargs["data"])
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset), request_data["asset_pair_name"])
        self.assertEqual(BigoneExchange.bigone_order_type(OrderType.LIMIT), request_data["type"])
        self.assertEqual(Decimal("100"), Decimal(request_data["amount"]))
        self.assertEqual(Decimal("10000"), Decimal(request_data["price"]))
        self.assertEqual(order.client_order_id, request_data["client_order_id"])

    def validate_order_cancelation_request(self, order: InFlightOrder, request_call: RequestCall):
        request_data = json.loads(request_call.kwargs["data"])
        self.assertEqual(order.client_order_id, request_data["client_order_id"])

    def validate_order_status_request(self, order: InFlightOrder, request_call: RequestCall):
        request_params = request_call.kwargs["params"]
        self.assertEqual(order.client_order_id, request_params["client_order_id"])

    def validate_trades_request(self, order: InFlightOrder, request_call: RequestCall):
        request_params = request_call.kwargs["params"]
        self.assertEqual(self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                         request_params["asset_pair_name"])

    def configure_successful_cancelation_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.CANCEL_ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_cancelation_request_successful_mock_response(order=order)
        mock_api.post(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_erroneous_cancelation_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.CANCEL_ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        mock_api.post(regex_url, status=400, callback=callback)
        return url

    def configure_order_not_found_error_cancelation_response(
        self, order: InFlightOrder, mock_api: aioresponses, callback: Optional[Callable] = lambda *args, **kwargs: None
    ) -> str:
        url = web_utils.private_rest_url(CONSTANTS.CANCEL_ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = {"code": -2011, "msg": "Unknown order sent."}
        mock_api.post(regex_url, status=400, body=json.dumps(response), callback=callback)
        return url

    def configure_one_successful_one_erroneous_cancel_all_response(
            self,
            successful_order: InFlightOrder,
            erroneous_order: InFlightOrder,
            mock_api: aioresponses) -> List[str]:
        """
        :return: a list of all configured URLs for the cancelations
        """
        all_urls = []
        url = self.configure_successful_cancelation_response(order=successful_order, mock_api=mock_api)
        all_urls.append(url)
        url = self.configure_erroneous_cancelation_response(order=erroneous_order, mock_api=mock_api)
        all_urls.append(url)
        return all_urls

    def configure_completely_filled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_status_request_completely_filled_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_canceled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_status_request_canceled_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_erroneous_http_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(path_url=CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = re.compile(url + r"\?.*")
        mock_api.get(regex_url, status=400, callback=callback)
        return url

    def configure_open_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        """
        :return: the URL configured
        """
        url = web_utils.private_rest_url(CONSTANTS.ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_status_request_open_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_http_error_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        mock_api.get(regex_url, status=401, callback=callback)
        return url

    def configure_partially_filled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = self._order_status_request_partially_filled_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_order_not_found_error_order_status_response(
        self, order: InFlightOrder, mock_api: aioresponses, callback: Optional[Callable] = lambda *args, **kwargs: None
    ) -> List[str]:
        url = web_utils.private_rest_url(CONSTANTS.ORDER_BY_ID_OR_CLIENT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        response = {"code": -2013, "msg": "Order does not exist."}
        mock_api.get(regex_url, body=json.dumps(response), status=400, callback=callback)
        return [url]

    def configure_partial_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(path_url=CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = f"{url}?asset_pair_name=COINALPHA-HBOT&limit=200"
        response = self._order_fills_request_partial_fill_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_full_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None) -> str:
        url = web_utils.private_rest_url(path_url=CONSTANTS.MY_TRADES_PATH_URL)
        regex_url = f"{url}?asset_pair_name=COINALPHA-HBOT&limit=200"
        response = self._order_fills_request_full_fill_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def order_event_for_new_order_websocket_update(self, order: InFlightOrder):
        return {
            "requestId": "1",
            "orderUpdate": {
                "order": {
                    "id": int(order.exchange_order_id),
                    "price": "10000",
                    "stopPrice": "0.0",
                    "amount": str(order.amount),
                    "market": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "side": order.order_type.name.upper(),
                    "state": "OPENING",
                    "filledAmount": "0.00000000",
                    "filledFees": "0.0",
                    "avgDealPrice": "9.0",
                    "clientOrderId": order.client_order_id,
                    "createdAt": "2018-09-12T09:52:36Z",
                    "updatedAt": "2018-09-12T09:52:37Z"
                }
            }
        }

    def order_event_for_canceled_order_websocket_update(self, order: InFlightOrder):
        return {
            "requestId": "1",
            "orderUpdate": {
                "order": {
                    "id": order.exchange_order_id,
                    "price": "10000",
                    "stopPrice": "0.0",
                    "amount": str(order.amount),
                    "market": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "side": order.order_type.name.upper(),
                    "state": "CANCELLED",
                    "filledAmount": "0.00000000",
                    "filledFees": "0.0",
                    "avgDealPrice": "0.0",
                    "clientOrderId": order.client_order_id,
                    "createdAt": "2018-09-12T09:52:36Z",
                    "updatedAt": "2018-09-12T09:52:37Z"
                }
            }
        }

    def order_event_for_full_fill_websocket_update(self, order: InFlightOrder):
        return {
            "requestId": "1",
            "orderUpdate": {
                "order": {
                    "id": int(order.exchange_order_id),
                    "price": "10000",
                    "stopPrice": "0.0",
                    "amount": str(order.amount),
                    "market": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "side": order.trade_type.name.upper(),
                    "state": "FILLED",
                    "filledAmount": str(order.amount),
                    "filledFees": "10000",
                    "avgDealPrice": "0.0",
                    "clientOrderId": order.client_order_id,
                    "createdAt": "2018-09-12T09:52:36Z",
                    "updatedAt": "2018-09-12T09:52:37Z"
                }
            }
        }

    def trade_event_for_full_fill_websocket_update(self, order: InFlightOrder):
        return {
            "requestId": "1",
            "tradeUpdate": {
                "trade": {
                    "id": int(self.expected_fill_trade_id),
                    "price": str(order.price),
                    "amount": str(order.amount),
                    "market": self.exchange_trading_pair,
                    "createdAt": "2018-09-12T09:52:37Z",
                    "makerOrder": None,
                    "takerOrder": {
                        "id": order.exchange_order_id,
                        "price": str(order.price),
                        "stopPrice": "",
                        "amount": str(order.amount),
                        "market": "",
                        "side": "BID",
                        "state": "FILLED",
                        "filledAmount": Decimal(order.amount),
                        "filledFees": str(self.expected_fill_fee.flat_fees[0].amount),
                        "avgDealPrice": "",
                        "clientOrderId": order.client_order_id,
                        "createdAt": None,
                        "updatedAt": None,
                        "businessUnit": "SPOT",
                        "type": "LIMIT",
                        "operator": "LTE",
                        "ioc": False
                    },
                    "takerSide": "BID"
                }
            }
        }

    @aioresponses()
    @patch("hummingbot.connector.time_synchronizer.TimeSynchronizer._current_seconds_counter")
    def test_update_time_synchronizer_successfully(self, mock_api, seconds_counter_mock):
        request_sent_event = asyncio.Event()
        seconds_counter_mock.side_effect = [0, 0, 0]

        self.exchange._time_synchronizer.clear_time_offset_ms_samples()
        url = web_utils.private_rest_url(CONSTANTS.SERVER_TIME_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        response = {
            "data": {
                "Timestamp": 1527665262168391000
            }
        }

        mock_api.get(regex_url,
                     body=json.dumps(response),
                     callback=lambda *args, **kwargs: request_sent_event.set())

        self.async_run_with_timeout(self.exchange._update_time_synchronizer())

        self.assertEqual(response["data"]["Timestamp"] * 1e-3, self.exchange._time_synchronizer.time())

    @aioresponses()
    def test_update_time_synchronizer_failure_is_logged(self, mock_api):
        request_sent_event = asyncio.Event()

        url = web_utils.private_rest_url(CONSTANTS.SERVER_TIME_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        response = {"code": -1121, "msg": "Dummy error"}

        mock_api.get(regex_url,
                     body=json.dumps(response),
                     callback=lambda *args, **kwargs: request_sent_event.set())

        self.async_run_with_timeout(self.exchange._update_time_synchronizer())

        self.assertTrue(self.is_logged("NETWORK", "Error getting server time."))

    @aioresponses()
    def test_update_time_synchronizer_raises_cancelled_error(self, mock_api):
        url = web_utils.private_rest_url(CONSTANTS.SERVER_TIME_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))

        mock_api.get(regex_url,
                     exception=asyncio.CancelledError)

        self.assertRaises(
            asyncio.CancelledError,
            self.async_run_with_timeout, self.exchange._update_time_synchronizer())

    @patch("hummingbot.connector.exchange.bigone.bigone_exchange.BigoneExchange._all_trade_updates_for_orders", callable=AsyncMock)
    @aioresponses()
    def test_update_order_status_when_failed(self, mock_fills, mock_api):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)

        request_sent_event = asyncio.Event()
        self.exchange._set_current_timestamp(1640780000)
        self.exchange.start_tracking_order(
            order_id="OID1",
            exchange_order_id="100234",
            trading_pair=self.trading_pair,
            order_type=OrderType.LIMIT,
            trade_type=TradeType.BUY,
            price=Decimal("10000"),
            amount=Decimal("1"),
        )
        order = self.exchange.in_flight_orders["OID1"]

        url = self.configure_partial_fill_trade_response(
            order=order,
            mock_api=mock_api,
            callback=lambda *args, **kwargs: request_sent_event.set())

        mock_fills.return_value = self._order_fills_request_mock_response(order)
        task = self.ev_loop.create_task(self.exchange._all_trade_updates_for_orders(order))

        self.async_run_with_timeout(task)

        url = web_utils.private_rest_url(CONSTANTS.ORDER_BY_ID_OR_CLIENT)

        order_status = {
            "data": {
                "id": int(order.exchange_order_id),
                "asset_pair_name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                "price": "10000.0",
                "amount": "1.0",
                "filled_amount": "0.0",
                "avg_deal_price": "0.0",
                "side": "BID",
                "state": "REJECTED",
                "type": "LIMIT",
                "operator": "LTE",
                "immediate_or_cancel": False,
                "post_only": True,
                "clientOrderId": order.client_order_id,
                "created_at": "2019-01-29T06:05:56Z",
                "updated_at": "2019-01-29T06:05:56Z"
            }
        }
        mock_response = order_status
        url = f"{url}?client_order_id={order.client_order_id}"
        mock_api.get(url, body=json.dumps(mock_response))

        self.async_run_with_timeout(self.exchange._update_order_status())

        request = self._all_executed_requests(mock_api, url)[0]
        self.validate_auth_credentials_present(request)
        request_params = request.kwargs["params"]
        self.assertEqual(order.client_order_id, request_params["client_order_id"])

        failure_event: MarketOrderFailureEvent = self.order_failure_logger.event_log[0]

        self.assertEqual(self.exchange.current_timestamp, failure_event.timestamp)
        self.assertEqual(order.client_order_id, failure_event.order_id)
        self.assertEqual(order.order_type, failure_event.order_type)
        self.assertNotIn(order.client_order_id, self.exchange.in_flight_orders)
        # self.assertTrue(
        #     self.is_logged(
        #         "INFO",
        #         f"Order {order.client_order_id} has failed. Order Update: OrderUpdate(trading_pair='{self.trading_pair}',"
        #         f" update_timestamp={bigone_utils.datetime_val_or_now(order_status['data']['updated_at'], on_error_return_now=True).timestamp()}, new_state={repr(OrderState.FAILED)}, "
        #         f"client_order_id='{order.client_order_id}', exchange_order_id='{order.exchange_order_id}', "
        #         "misc_updates=None)")
        # )

    def test_user_stream_logs_errors(self):
        pass

    def test_user_stream_update_for_order_failure(self):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange.start_tracking_order(
            order_id="OID1",
            exchange_order_id="100234",
            trading_pair=self.trading_pair,
            order_type=OrderType.LIMIT,
            trade_type=TradeType.BUY,
            price=Decimal("10000"),
            amount=Decimal("1"),
        )
        order = self.exchange.in_flight_orders["OID1"]

        event_message = {
            "requestId": "1",
            "orderUpdate": {
                "order": {
                    "id": int(order.exchange_order_id),
                    "price": "1000.00000000",
                    "stopPrice": "0.0",
                    "amount": "1.00000000",
                    "market": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                    "side": "BID",
                    "state": "REJECTED",
                    "filledAmount": "0.0",
                    "filledFees": "0.0",
                    "avgDealPrice": "0.0",
                    "clientOrderId": order.client_order_id,
                    "createdAt": "2018-09-12T09:52:36Z",
                    "updatedAt": "2018-09-12T09:52:37Z"
                }
            }
        }

        mock_queue = AsyncMock()
        mock_queue.get.side_effect = [event_message, asyncio.CancelledError]
        self.exchange._user_stream_tracker._user_stream = mock_queue

        try:
            self.async_run_with_timeout(self.exchange._user_stream_event_listener())
        except asyncio.CancelledError:
            pass

        failure_event: MarketOrderFailureEvent = self.order_failure_logger.event_log[0]
        self.assertEqual(self.exchange.current_timestamp, failure_event.timestamp)
        self.assertEqual(order.client_order_id, failure_event.order_id)
        self.assertEqual(order.order_type, failure_event.order_type)
        self.assertNotIn(order.client_order_id, self.exchange.in_flight_orders)
        self.assertTrue(order.is_failure)
        self.assertTrue(order.is_done)

    @patch("hummingbot.connector.utils.get_tracking_nonce")
    def test_client_order_id_on_order(self, mocked_nonce):
        mocked_nonce.return_value = 7

        result = self.exchange.buy(
            trading_pair=self.trading_pair,
            amount=Decimal("1"),
            order_type=OrderType.LIMIT,
            price=Decimal("2"),
        )
        expected_client_order_id = get_new_client_order_id(
            is_buy=True,
            trading_pair=self.trading_pair,
            hbot_order_id_prefix=CONSTANTS.HBOT_ORDER_ID_PREFIX,
            max_id_len=CONSTANTS.MAX_ORDER_ID_LEN,
        )

        self.assertEqual(result, expected_client_order_id)

        result = self.exchange.sell(
            trading_pair=self.trading_pair,
            amount=Decimal("1"),
            order_type=OrderType.LIMIT,
            price=Decimal("2"),
        )
        expected_client_order_id = get_new_client_order_id(
            is_buy=False,
            trading_pair=self.trading_pair,
            hbot_order_id_prefix=CONSTANTS.HBOT_ORDER_ID_PREFIX,
            max_id_len=CONSTANTS.MAX_ORDER_ID_LEN,
        )

        self.assertEqual(result, expected_client_order_id)

    def test_time_synchronizer_related_request_error_detection(self):
        exception = IOError("Error executing request POST https://bigone.com/api/v3/order. HTTP status is 400. "
                            "Error: {'code':-1021,'msg':'Timestamp for this request is outside of the recvWindow.'}")
        self.assertTrue(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

        exception = IOError("Error executing request POST https://bigone.com/api/v3/order. HTTP status is 400. "
                            "Error: {'code':-1021,'msg':'Timestamp for this request was 1000ms ahead of the server's "
                            "time.'}")
        self.assertTrue(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

        exception = IOError("Error executing request POST https://bigone.com/api/v3/order. HTTP status is 400. "
                            "Error: {'code':-1022,'msg':'Timestamp for this request was 1000ms ahead of the server's "
                            "time.'}")
        self.assertFalse(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

        exception = IOError("Error executing request POST https://bigone.com/api/v3/order. HTTP status is 400. "
                            "Error: {'code':-1021,'msg':'Other error.'}")
        self.assertFalse(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

    @aioresponses()
    def test_place_order_manage_server_overloaded_error_unkown_order(self, mock_api):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)
        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        mock_response = {"code": -1003, "msg": "Unknown error, please check your request or try again later."}
        mock_api.post(regex_url, body=json.dumps(mock_response), status=503)

        o_id, transact_time = self.async_run_with_timeout(self.exchange._place_order(
            order_id="test_order_id",
            trading_pair=self.trading_pair,
            amount=Decimal("1"),
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("2"),
        ))
        self.assertEqual(o_id, "UNKNOWN")

    @aioresponses()
    def test_place_order_manage_server_overloaded_error_failure(self, mock_api):
        self.exchange._set_current_timestamp(1640780000)
        self.exchange._last_poll_timestamp = (self.exchange.current_timestamp -
                                              self.exchange.UPDATE_ORDER_STATUS_MIN_INTERVAL - 1)

        url = web_utils.private_rest_url(CONSTANTS.ORDER_PATH_URL)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?"))
        mock_response = {"code": -1003, "msg": "Service Unavailable."}
        mock_api.post(regex_url, body=json.dumps(mock_response), status=503)

        self.assertRaises(
            IOError,
            self.async_run_with_timeout,
            self.exchange._place_order(
                order_id="test_order_id",
                trading_pair=self.trading_pair,
                amount=Decimal("1"),
                trade_type=TradeType.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("2"),
            ))

        mock_response = {"code": -1003, "msg": "Internal error; unable to process your request. Please try again."}
        mock_api.post(url, body=json.dumps(mock_response), status=503)

        self.assertRaises(
            IOError,
            self.async_run_with_timeout,
            self.exchange._place_order(
                order_id="test_order_id",
                trading_pair=self.trading_pair,
                amount=Decimal("1"),
                trade_type=TradeType.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("2"),
            ))

    def _validate_auth_credentials_taking_parameters_from_argument(self,
                                                                   request_call_tuple: RequestCall,
                                                                   params: Dict[str, Any]):

        request_headers = request_call_tuple.kwargs["headers"]
        self.assertIn("Authorization", request_headers)
        self.assertIn("Bearer", request_headers["Authorization"])

    def _order_cancelation_request_successful_mock_response(self, order: InFlightOrder) -> Any:
        return {
            "data": {
                "id": int(order.exchange_order_id),
                "asset_pair_name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                "price": str(order.price),
                "amount": str(order.amount),
                "filled_amount": str(Decimal("0")),
                "avg_deal_price": str(Decimal("0")),
                "side": order.trade_type.name.upper(),
                "state": "CANCELLED",
                "type": "LIMIT",
                "operator": "LTE",
                "immediate_or_cancel": False,
                "post_only": True,
                "client_order_id": order.client_order_id,
                "created_at": "2019-01-29T06:05:56Z",
                "updated_at": "2019-01-29T06:05:56Z"
            }}

    def _order_status_request_completely_filled_mock_response(self, order: InFlightOrder) -> Any:
        return {
            "data": {
                "id": order.exchange_order_id,
                "asset_pair_name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                "price": str(order.price),
                "amount": str(order.amount),
                "filled_amount": str(order.amount),
                "avg_deal_price": "12.0",
                "side": order.trade_type.name.upper(),
                "state": "FILLED",
                "type": "LIMIT",
                "operator": "LTE",
                "immediate_or_cancel": False,
                "post_only": True,
                "client_order_id": order.client_order_id,
                "created_at": "2019-01-29T06:05:56Z",
                "updated_at": "2019-01-29T06:05:56Z"
            }
        }

    def _order_status_request_canceled_mock_response(self, order: InFlightOrder) -> Any:
        return {
            "data": {
                "id": int(order.exchange_order_id),
                "asset_pair_name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                "price": str(order.price),
                "amount": str(order.amount),
                "filled_amount": str(order.amount),
                "avg_deal_price": "12.0",
                "side": order.trade_type.name.upper(),
                "state": "CANCELLED",
                "type": "LIMIT",
                "operator": "LTE",
                "immediate_or_cancel": False,
                "post_only": True,
                "client_order_id": order.client_order_id,
                "created_at": "2019-01-29T06:05:56Z",
                "updated_at": "2019-01-29T06:05:56Z"
            }
        }

    def _order_status_request_open_mock_response(self, order: InFlightOrder) -> Any:
        return {
            "data": {
                "id": int(order.exchange_order_id),
                "asset_pair_name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                "price": str(order.price),
                "amount": str(order.amount),
                "filled_amount": str(order.amount),
                "avg_deal_price": "0.0",
                "side": order.trade_type.name.upper(),
                "state": "OPENING",
                "type": "LIMIT",
                "operator": "LTE",
                "immediate_or_cancel": False,
                "post_only": True,
                "client_order_id": order.client_order_id,
                "created_at": "2019-01-29T06:05:56Z",
                "updated_at": "2019-01-29T06:05:56Z"
            }
        }

    def _order_status_request_partially_filled_mock_response(self, order: InFlightOrder) -> Any:
        return {
            "data": {
                "id": int(order.exchange_order_id),
                "asset_pair_name": self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset),
                "price": str(order.price),
                "amount": str(order.amount),
                "filled_amount": str(order.amount),
                "avg_deal_price": "0.0",
                "side": order.trade_type.name.upper(),
                "state": "PENDING",
                "type": "LIMIT",
                "operator": "LTE",
                "immediate_or_cancel": False,
                "post_only": True,
                "client_order_id": order.client_order_id,
                "created_at": "2019-01-29T06:05:56Z",
                "updated_at": "2019-01-29T06:05:56Z"
            }
        }

    def _order_fills_request_partial_fill_mock_response(self, order: InFlightOrder):
        return {
            "data":
                [
                    {
                        "id": self.expected_fill_trade_id,
                        "asset_pair_name": self.exchange_symbol_for_tokens(order.base_asset, order.quote_asset),
                        "price": str(self.expected_partial_fill_price),
                        "amount": str(self.expected_partial_fill_amount),
                        "taker_side": "BID",
                        "maker_order_id": int(order.exchange_order_id),
                        "taker_order_id": 58284909,
                        "maker_fee": str(self.expected_fill_fee.flat_fees[0].amount),
                        "taker_fee": None,
                        "side": "SELF_TRADING",
                        "inserted_at": "2019-04-16T12:00:01Z"
                    }
                ],
                "page_token": "dxzef"
        }

    def _order_fills_request_mock_response(self, order: InFlightOrder):
        return [
            {
                "id": self.expected_fill_trade_id,
                "asset_pair_name": self.exchange_symbol_for_tokens(order.base_asset, order.quote_asset),
                "price": str(self.expected_partial_fill_price),
                "amount": str(self.expected_partial_fill_amount),
                "taker_side": "BID",
                "maker_order_id": int(order.exchange_order_id),
                "taker_order_id": 58284909,
                "maker_fee": str(self.expected_fill_fee.flat_fees[0].amount),
                "taker_fee": None,
                "side": "SELF_TRADING",
                "inserted_at": "2019-04-16T12:00:01Z"
            }
        ]

    def _order_fills_request_full_fill_mock_response(self, order: InFlightOrder):
        return {
            "data":
            [
                {
                    "id": int(self.expected_fill_trade_id),
                    "asset_pair_name": self.exchange_symbol_for_tokens(order.base_asset, order.quote_asset),
                    "price": str(order.price),
                    "amount": str(order.amount),
                    "taker_side": "BID",
                    "maker_order_id": int(order.exchange_order_id),
                    "taker_order_id": 58284909,
                    "maker_fee": str(self.expected_fill_fee.flat_fees[0].amount),
                    "taker_fee": None,
                    "side": "SELF_TRADING",
                    "inserted_at": "2019-04-16T12:00:01Z"
                }
            ],
            "page_token": "dxzef"
        }
