from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

DEFAULT_DOMAIN = "biconomy"

HBOT_ORDER_ID_PREFIX = "x-XEKWYICX"
MAX_ORDER_ID_LEN = 32

# Base URL
REST_URL = "https://market.biconomy.vip/api/"
WSS_URL = "wss://www.biconomy.com/ws"

PUBLIC_API_VERSION = "v1"
PRIVATE_API_VERSION = "v2"
PING_TIMEOUT = 3
# Public API endpoints or BiconomyClient function
TICKER_PRICE_CHANGE_PATH_URL = "/tickers"
TICKER_BOOK_PATH_URL = "/tickers"
EXCHANGE_INFO_PATH_URL = "/exchangeInfo"
PING_PATH_URL = "/ping"
SNAPSHOT_PATH_URL = "/depth"

# Private API endpoints or BiconomyClient function
ACCOUNTS_PATH_URL = "/private/user"
MY_TRADES_PATH_URL = "/private/order/deals"
TRADE_PATH_URL = "/private/trade/{}"
ORDER_PATH_URL = "/private/order/{}"
ORDER_STATUS = "/private/order/{}/detail"
CANCEL_ORDER_PATH_URL = "/private/trade/cancel"
BICONOMY_USER_STREAM_PATH_URL = "/userDataStream"

USER_ASSET_ENDPOINT_NAME = "asset.update"
USER_ORDERS_ENDPOINT_NAME = "order.update"
SERVER_SIGN = "server.sign"

WS_HEARTBEAT_TIME_INTERVAL = 30

# Biconomy params

SIDE_BUY = "1"
SIDE_SELL = "2"

TIME_IN_FORCE_GTC = "GTC"  # Good till cancelled
TIME_IN_FORCE_IOC = "IOC"  # Immediate or cancel
TIME_IN_FORCE_FOK = "FOK"  # Fill or kill

# Rate Limit time intervals
ONE_MINUTE = 60
ONE_SECOND = 1
ONE_DAY = 86400

MAX_REQUEST = 5000

# Order States
ORDER_STATE = {
    "created": OrderState.PENDING_CREATE,
    "finished": OrderState.FILLED,
    "pending": OrderState.PARTIALLY_FILLED,
    "canceled": OrderState.CANCELED
}

# Websocket event types
DIFF_EVENT_TYPE = "depth.update"
TRADE_EVENT_TYPE = "trade"

RATE_LIMITS = [
    RateLimit(limit_id=PING_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=EXCHANGE_INFO_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=TICKER_PRICE_CHANGE_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=TICKER_BOOK_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=SNAPSHOT_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=BICONOMY_USER_STREAM_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=ACCOUNTS_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=10, time_interval=ONE_SECOND),
    RateLimit(limit_id=ORDER_STATUS, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=CANCEL_ORDER_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=ORDER_PATH_URL, limit=20, time_interval=ONE_SECOND),
    RateLimit(limit_id=TRADE_PATH_URL, limit=20, time_interval=ONE_SECOND),
]

ORDER_NOT_EXIST_ERROR_CODE = -2013
ORDER_NOT_EXIST_MESSAGE = "Order does not exist"
UNKNOWN_ORDER_ERROR_CODE = -2011
UNKNOWN_ORDER_MESSAGE = "Unknown order sent"
