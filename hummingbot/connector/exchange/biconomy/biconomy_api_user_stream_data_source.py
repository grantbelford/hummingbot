from typing import TYPE_CHECKING, Any, Dict, List, Optional
import asyncio
import hashlib
import hmac
import time

from hummingbot.connector.exchange.biconomy import biconomy_constants as CONSTANTS
from hummingbot.connector.exchange.biconomy.biconomy_auth import BiconomyAuth
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.ascend_ex.biconomy_exchange import BiconomyExchange


class BiconomyAPIUserStreamDataSource(UserStreamTrackerDataSource):
    _logger: Optional[HummingbotLogger] = None

    def __init__(self,
                 auth: BiconomyAuth,
                 trading_pairs: List[str],
                 connector: 'BiconomyExchange',
                 api_factory: WebAssistantsFactory,
                 domain: str = CONSTANTS.DEFAULT_DOMAIN):

        super().__init__()
        self._auth: BiconomyAuth = auth
        self._current_auth_token = None
        self._connector = connector
        self._domain = domain
        self._trading_pairs = trading_pairs
        self._api_factory = api_factory

    async def _connected_websocket_assistant(self) -> WSAssistant:
        ws: WSAssistant = await self._api_factory.get_ws_assistant()
        await ws.connect(ws_url=CONSTANTS.WSS_URL, ping_timeout=CONSTANTS.PING_TIMEOUT)
        return ws

    @property
    def last_recv_time(self):
        if self._ws_assistant is None:
            return 0
        else:
            return self._ws_assistant.last_recv_time

    async def _subscribe_channels(self, websocket_assistant: WSAssistant):
        """
        Subscribes to order events and balance events.

        :param websocket_assistant: the websocket assistant used to connect to the exchange
        """
        try:
            timestamp = int(time.time() * 1000)
            message = f"api_key={self._auth.api_key}&secret_key={self._auth.secret_key}&timestamp={timestamp}"
            hmac_key = self._auth.secret_key.encode()
            message = message.encode()
            signature = hmac.new(hmac_key, message, hashlib.sha256).hexdigest()

            payload = {
                "method": "server.sign",
                "params": [self._auth.api_key, signature, timestamp],
                "id": 1
            }
            subscribe_auth_request = WSJSONRequest(payload=payload)
            await websocket_assistant.send(subscribe_auth_request)
            await asyncio.sleep(3)

            symbol = []
            for pair in self._trading_pairs:
                trading_pair = await self._connector.exchange_symbol_associated_to_pair(trading_pair=pair)
                symbol.append(trading_pair)

            # order subcription
            trades_payload = {"method": "order.subscribe", "params": [], "id": 9605}
            subscribe_trades_request: WSJSONRequest = WSJSONRequest(payload=trades_payload)

            # Balance subcription
            base, quote = symbol[0].split("_")
            balance_payload = {"method": "asset.subscribe", "params": [base, quote], "id": 9615}
            subscribe_balance_request: WSJSONRequest = WSJSONRequest(payload=balance_payload)

            await websocket_assistant.send(subscribe_trades_request)
            await websocket_assistant.send(subscribe_balance_request)

            self.logger().info("Subscribed to private order changes and trades updates channels...")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger().exception("Unexpected error occurred subscribing to user streams...")
            raise

    async def _send_ping(self, websocket_assistant: WSAssistant):
        payload = {
            "method": "server.ping",
            "params": [],
            "id": 5160
        }
        ping_request: WSJSONRequest = WSJSONRequest(payload=payload)
        await websocket_assistant.send(ping_request)

    async def _process_event_message(self, event_message: Dict[str, Any], queue: asyncio.Queue):
        if "result" in event_message or "params" in event_message:
            queue.put_nowait(event_message)
        else:
            if event_message.get("error") is not None:
                err_msg = event_message["result"].get("message")
                raise IOError({
                    "label": "WSS_ERROR",
                    "message": f"Error received via websocket - {err_msg}."
                })
