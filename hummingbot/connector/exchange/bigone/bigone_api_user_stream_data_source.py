import asyncio
import json
import time
from typing import TYPE_CHECKING, Dict, List, Optional

import jwt

from hummingbot.connector.exchange.bigone import bigone_constants as CONSTANTS
from hummingbot.connector.exchange.bigone.bigone_auth import BigoneAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.bigone.bigone_exchange import BigoneExchange


class BigoneAPIUserStreamDataSource(UserStreamTrackerDataSource):

    LISTEN_KEY_KEEP_ALIVE_INTERVAL = 1800  # Recommended to Ping/Update listen key to keep connection alive
    HEARTBEAT_TIME_INTERVAL = 30.0

    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: BigoneAuth,
                 trading_pairs: List[str],
                 connector: 'BigoneExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):
        super().__init__()
        self._trading_pairs = trading_pairs
        self._connector = connector
        self._auth: BigoneAuth = auth
        self._current_listen_key = None
        self._domain = domain
        self._api_factory = api_factory

        self._listen_key_initialized_event: asyncio.Event = asyncio.Event()
        self._last_listen_key_ping_ts = 0

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL, ping_timeout=CONSTANTS.PING_TIMEOUT, ws_headers={"Sec-WebSocket-Protocol": "json"})
        return ws

    def _get_auth_headers_ws(self) -> Dict[str, str]:
        nonce = int(time.time() * 1e9)
        # JWT payload
        payload = {
            "type": "OpenAPIV2",
            "sub": f"{self._auth.api_key}",
            "nonce": str(nonce)
        }
        token = jwt.encode(payload, self._auth.secret_key, algorithm="HS256")
        header = f'Bearer {token}'
        return header

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Subscribes to order events.
        :param websocket_assistant: the websocket assistant used to connect to the exchange
        """
        try:
            user_info_symbols = []
            for trading_pair in self._trading_pairs:
                symbol = await self._connector.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
            user_info_symbols.append(symbol)

            orders_change_payload = {"requestId": "1", "authenticateCustomerRequest": {"token": f"{self._get_auth_headers_ws()}"}}
            subscribe_auth_request: WSJSONRequest = WSJSONRequest(
                payload=orders_change_payload)

            orders_change_payload = {"requestId": "1", "subscribeViewerOrdersRequest": {"market": f'{user_info_symbols[0]}'}}
            subscribe_order_change_request: WSJSONRequest = WSJSONRequest(
                payload=orders_change_payload)

            trades_payload = {"requestId": "1", "subscribeMarketTradesRequest": {"market": f'{user_info_symbols[0]}', "limit": "20"}}
            subscribe_trades_request: WSJSONRequest = WSJSONRequest(
                payload=trades_payload)
            account_payload = {"requestId": "1", "subscribeViewerAccountsRequest": {}}
            subscribe_account_request: WSJSONRequest = WSJSONRequest(
                payload=account_payload)
            await websocket_assistant.send(subscribe_auth_request)
            await asyncio.sleep(3)
            await websocket_assistant.send(subscribe_order_change_request)
            await websocket_assistant.send(subscribe_trades_request)
            await websocket_assistant.send(subscribe_account_request)

            self.logger().info("Subscribed to private order changes channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error occurred subscribing to user streams...")
            raise

    async def _process_event_message(self, event_message: bytes, queue: asyncio.Queue):
        msg = event_message.decode('utf-8')
        message = json.loads(msg)
        if "error" in message:
            err_msg = message.get("error", {}).get("message", message.get("error"))
            raise IOError({
                "label": "WSS_ERROR",
                "message": f"Error received via websocket - {err_msg}."
            })
        if "success" not in message:
            # Check for update types in message
            if "tradeUpdate" in message:
                await queue.put(message)
            elif "orderUpdate" in message:
                await queue.put(message)
            elif "accountUpdate" in message:
                await queue.put(message)
