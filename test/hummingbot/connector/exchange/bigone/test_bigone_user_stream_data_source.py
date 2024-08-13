import asyncio
import json
import unittest
from typing import Awaitable, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from bidict import bidict

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.bigone import bigone_constants as CONSTANTS
from hummingbot.connector.exchange.bigone.bigone_api_user_stream_data_source import BigoneAPIUserStreamDataSource
from hummingbot.connector.exchange.bigone.bigone_auth import BigoneAuth
from hummingbot.connector.exchange.bigone.bigone_exchange import BigoneExchange
from hummingbot.connector.test_support.network_mocking_assistant import NetworkMockingAssistant
from hummingbot.connector.time_synchronizer import TimeSynchronizer
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler


class TestBigoneAPIUserStreamDataSource(unittest.TestCase):
    # the level is required to receive logs from the data source logger
    level = 0

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ev_loop = asyncio.get_event_loop()
        cls.base_asset = "COINALPHA"
        cls.quote_asset = "HBOT"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.api_key = "someKey"
        cls.api_secret_key = "someSecretKey"

    def setUp(self) -> None:
        super().setUp()
        self.log_records = []
        self.listening_task: Optional[asyncio.Task] = None
        self.mocking_assistant = NetworkMockingAssistant()

        self.throttler = AsyncThrottler(CONSTANTS.RATE_LIMITS)
        self.mock_time_provider = MagicMock()
        self.mock_time_provider.time.return_value = 1000
        self.auth = BigoneAuth(
            api_key=self.api_key,
            secret_key=self.api_secret_key,
            time_provider=self.mock_time_provider)
        self.time_synchronizer = TimeSynchronizer()
        self.time_synchronizer.add_time_offset_ms_sample(0)

        client_config_map = ClientConfigAdapter(ClientConfigMap())
        self.connector = BigoneExchange(
            client_config_map=client_config_map,
            bigone_api_key="",
            bigone_api_secret="",
            trading_pairs=[],
            trading_required=False,
            domain = CONSTANTS.DEFAULT_DOMAIN)
        self.connector._web_assistants_factory._auth = self.auth

        self.data_source = BigoneAPIUserStreamDataSource(
            self.auth,
            trading_pairs=[self.trading_pair],
            connector=self.connector,
            api_factory=self.connector._web_assistants_factory)

        self.data_source.logger().setLevel(1)
        self.data_source.logger().addHandler(self)

        self.connector._set_trading_pair_symbol_map(bidict({self.ex_trading_pair: self.trading_pair}))

    def tearDown(self) -> None:
        self.listening_task and self.listening_task.cancel()
        super().tearDown()

    def handle(self, record):
        self.log_records.append(record)

    def _is_logged(self, log_level: str, message: str) -> bool:
        return any(record.levelname == log_level and record.getMessage() == message
                   for record in self.log_records)

    def async_run_with_timeout(self, coroutine: Awaitable, timeout: int = 1):
        ret = self.ev_loop.run_until_complete(asyncio.wait_for(coroutine, timeout))
        return ret

    @patch('time.time', return_value=1234567890)
    @patch('jwt.encode')
    def test_get_auth_headers_ws(self, mock_jwt_encode, mock_time):
        # Prepare expected values
        nonce = int(mock_time.return_value * 1e9)
        expected_payload = {
            "type": "OpenAPIV2",
            "sub": self.api_key,
            "nonce": str(nonce)
        }
        expected_token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0eXBlIjoiT3BlbkFQSVYyIiwic3ViIjoic29tZUtleSIsIm5vbmNlIjoiMTcyMzQyNTMyMDM3OTk4ODk5MiJ9.Fl4_jZCBwys2-2ObprUjpHXISKvkihH71ogm3rs3sVk"
        mock_jwt_encode.return_value = expected_token

        # Expected header
        expected_header = f'Bearer {expected_token}'

        # Call the method
        header = self.data_source._get_auth_headers_ws()
        print(header)

        # Assertions
        mock_jwt_encode.assert_called_once_with(expected_payload, self.api_secret_key, algorithm="HS256")
        self.assertEqual(header, expected_header)

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    @patch("hummingbot.connector.exchange.bigone.bigone_api_user_stream_data_source.BigoneAPIUserStreamDataSource"
           "._time")
    @patch('time.time', return_value=1234567890)
    @patch('jwt.encode')
    def test_listen_for_user_stream_subscribes_to_orders_and_balances_events(self, mock_jwt_encode, mock_time, time_mock, ws_connect_mock):
        time_mock.return_value = 1000
        ws_connect_mock.return_value = self.mocking_assistant.create_websocket_mock()

        nonce = int(mock_time.return_value * 1e9)
        expected_payload = {
            "type": "OpenAPIV2",
            "sub": self.api_key,
            "nonce": str(nonce)
        }
        expected_token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0eXBlIjoiT3BlbkFQSVYyIiwic3ViIjoic29tZUtleSIsIm5vbmNlIjoiMTcyMzQyNTMyMDM3OTk4ODk5MiJ9.Fl4_jZCBwys2-2ObprUjpHXISKvkihH71ogm3rs3sVk"
        mock_jwt_encode.return_value = expected_token

        # Call the method
        header = self.data_source._get_auth_headers_ws()
        # Assertions
        mock_jwt_encode.assert_called_once_with(expected_payload, self.api_secret_key, algorithm="HS256")

        token = header
        result_subscribe_orders = json.dumps({
            "requestId": "1",
            "ordersSnapshot": {
                "orders": [
                    {
                        "id": "42844576",
                        "price": "9.0",
                        "stopPrice": "0.0",
                        "amount": "10000.0",
                        "market": "BTC-USDT",
                        "side": "ASK",
                        "state": "FILLED",
                        "filledAmount": "10000.0",
                        "filledFees": "90.0",
                        "avgDealPrice": "9.0",
                        "createdAt": "2018-09-12T09:52:36Z",
                        "updatedAt": "2018-09-12T09:52:37Z"
                    }
                ]
            }
        }).encode('utf-8')
        result_subscribe_trades = json.dumps({
            "requestId": "1",
            "tradesSnapshot": {
                "trades": [
                    {
                        "id": "28622",
                        "price": "9.0",
                        "amount": "10000.0",
                        "market": "BTC-USDT",
                        "createdAt": "2018-09-12T09:52:37Z",
                        "makerOrder": None,
                        "takerOrder": None,
                        "takerSide": "BID"
                    }
                ]
            }
        }).encode('utf-8')

        result_subscribe_balance = json.dumps({
            "requestId": "1",
            "accountsSnapshot": {
                "accounts": [
                    {
                        "asset": "BTC",
                        "balance": "10.0",
                        "lockedBalance": "0.0"
                    }
                ]
            }
        }).encode('utf-8')

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=result_subscribe_orders)
        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=result_subscribe_trades)
        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=result_subscribe_balance)

        output_queue = asyncio.Queue()

        self.listening_task = self.ev_loop.create_task(self.data_source.listen_for_user_stream(output=output_queue))

        self.mocking_assistant.run_until_all_aiohttp_messages_delivered(ws_connect_mock.return_value)

        sent_subscription_messages = self.mocking_assistant.json_messages_sent_through_websocket(
            websocket_mock=ws_connect_mock.return_value)

        self.assertEqual(4, len(sent_subscription_messages))
        expected_auth_subscription = {
            "requestId": "1",
            "authenticateCustomerRequest": {"token": f"{token}"}
        }
        self.assertEqual(expected_auth_subscription, sent_subscription_messages[0])
        expected_orders_subscription = {
            "requestId": "1",
            "subscribeViewerOrdersRequest": {"market": f'{self.ex_trading_pair}'}
        }
        self.assertEqual(expected_orders_subscription, sent_subscription_messages[1])
        expected_trades_subscription = {
            "requestId": "1",
            "subscribeMarketTradesRequest": {"market": f'{self.ex_trading_pair}', "limit": "20"}
        }
        self.assertEqual(expected_trades_subscription, sent_subscription_messages[2])
        expected_balance_subscription = {
            "requestId": "1",
            "subscribeViewerAccountsRequest": {}
        }
        self.assertEqual(expected_balance_subscription, sent_subscription_messages[3])
        self.assertTrue(self._is_logged(
            "INFO",
            "Subscribed to private order changes and balance updates channels..."
        ))

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    @patch("hummingbot.connector.exchange.bigone.bigone_api_user_stream_data_source.BigoneAPIUserStreamDataSource"
           "._time")
    def test_listen_for_user_stream_skips_subscribe_unsubscribe_messages(self, time_mock, ws_connect_mock):
        time_mock.return_value = 1000
        ws_connect_mock.return_value = self.mocking_assistant.create_websocket_mock()

        result_subscribe_orders = json.dumps({
            "requestId": "1",
            "ordersSnapshot": {
                "orders": [
                    {
                        "id": "42844576",
                        "price": "9.0",
                        "stopPrice": "0.0",
                        "amount": "10000.0",
                        "market": "BTC-USDT",
                        "side": "ASK",
                        "state": "FILLED",
                        "filledAmount": "10000.0",
                        "filledFees": "90.0",
                        "avgDealPrice": "9.0",
                        "createdAt": "2018-09-12T09:52:36Z",
                        "updatedAt": "2018-09-12T09:52:37Z"
                    }
                ]
            }
        }).encode('utf-8')
        result_subscribe_trades = json.dumps({
            "requestId": "1",
            "tradesSnapshot": {
                "trades": [
                    {
                        "id": "28622",
                        "price": "9.0",
                        "amount": "10000.0",
                        "market": "BTC-USDT",
                        "createdAt": "2018-09-12T09:52:37Z",
                        "makerOrder": None,
                        "takerOrder": None,
                        "takerSide": "BID"
                    }
                ]
            }
        }).encode('utf-8')
        result_subscribe_balance = json.dumps({
            "requestId": "1",
            "accountsSnapshot": {
                "accounts": [
                    {
                        "asset": "BTC",
                        "balance": "10.0",
                        "lockedBalance": "0.0"
                    }
                ]
            }
        }).encode('utf-8')

        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=result_subscribe_orders)
        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=result_subscribe_trades)
        self.mocking_assistant.add_websocket_aiohttp_message(
            websocket_mock=ws_connect_mock.return_value,
            message=result_subscribe_balance)

        output_queue = asyncio.Queue()

        self.listening_task = self.ev_loop.create_task(self.data_source.listen_for_user_stream(output=output_queue))

        self.mocking_assistant.run_until_all_aiohttp_messages_delivered(ws_connect_mock.return_value)

        self.assertTrue(output_queue.empty())

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    def test_listen_for_user_stream_does_not_queue_pong_payload(self, mock_ws):
        mock_pong = json.dumps({
            "id": 1,
            "channel": "pong",
        }).encode('utf-8')

        mock_ws.return_value = self.mocking_assistant.create_websocket_mock()
        self.mocking_assistant.add_websocket_aiohttp_message(mock_ws.return_value, mock_pong)

        msg_queue = asyncio.Queue()
        self.listening_task = self.ev_loop.create_task(
            self.data_source.listen_for_user_stream(msg_queue)
        )

        self.mocking_assistant.run_until_all_aiohttp_messages_delivered(mock_ws.return_value)

        self.assertEqual(0, msg_queue.qsize())

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    @patch("hummingbot.core.data_type.user_stream_tracker_data_source.UserStreamTrackerDataSource._sleep")
    def test_listen_for_user_stream_connection_failed(self, sleep_mock, mock_ws):
        mock_ws.side_effect = Exception("TEST ERROR.")
        sleep_mock.side_effect = asyncio.CancelledError  # to finish the task execution

        msg_queue = asyncio.Queue()
        try:
            self.async_run_with_timeout(self.data_source.listen_for_user_stream(msg_queue))
        except asyncio.CancelledError:
            pass

        self.assertTrue(
            self._is_logged("ERROR",
                            "Unexpected error while listening to user stream. Retrying after 5 seconds..."))

    @patch("aiohttp.ClientSession.ws_connect", new_callable=AsyncMock)
    @patch("hummingbot.core.data_type.user_stream_tracker_data_source.UserStreamTrackerDataSource._sleep")
    def test_listen_for_user_stream_iter_message_throws_exception(self, sleep_mock, mock_ws):
        msg_queue: asyncio.Queue = asyncio.Queue()
        mock_ws.return_value = self.mocking_assistant.create_websocket_mock()
        mock_ws.return_value.receive.side_effect = Exception("TEST ERROR")
        sleep_mock.side_effect = asyncio.CancelledError  # to finish the task execution

        try:
            self.async_run_with_timeout(self.data_source.listen_for_user_stream(msg_queue))
        except asyncio.CancelledError:
            pass

        self.assertTrue(
            self._is_logged(
                "ERROR",
                "Unexpected error while listening to user stream. Retrying after 5 seconds..."))
