from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.data_type.in_flight_order import OrderState

DEFAULT_DOMAIN = "com"

HBOT_ORDER_ID_PREFIX = "x-BigOneV3"
MAX_ORDER_ID_LEN = 32

# Base URL
REST_URL = "https://bigone.com/api/"
WSS_URL = "wss://bigone.com/ws/v2"

PUBLIC_API_VERSION = "v3"
PRIVATE_API_VERSION = "v3"
PING_TIMEOUT = 10.0

# Public API endpoints or BigoneClient function
TICKER_PRICE_CHANGE_PATH_URL = "/asset_pairs/tickers"
TICKER_BOOK_PATH_URL = "/{}/tickers"
EXCHANGE_INFO_PATH_URL = "/asset_pairs"
PING_PATH_URL = "/ping"
SNAPSHOT_PATH_URL = "/asset_pairs/{}/depth"
SERVER_TIME_PATH_URL = "/ping"

# Private API endpoints or BigoneClient function
ACCOUNTS_PATH_URL = "/viewer/accounts"
MY_TRADES_PATH_URL = "/viewer/trades"
ORDER_PATH_URL = "/viewer/orders"
ORDER_LIST_URL = "/viewer/orders"
SINGLE_ORDER = "/viewer/orders/{}"
CANCEL_ORDER = "/viewer/orders/{}/cancel"
CANCEL_ORDER_BY_ID_OR_CLIENT = "/viewer/order/cancel"
ORDER_BY_ID_OR_CLIENT = "/viewer/order"
BIGONE_USER_STREAM_PATH_URL = "/userDataStream"

WS_HEARTBEAT_TIME_INTERVAL = 30

USER_TRADES_ENDPOINT_NAME = "tradeUpdate"
USER_ORDERS_ENDPOINT_NAME = "orderUpdate"
USER_BALANCE_ENDPOINT_NAME = "accountUpdate"
# Bigone params

SIDE_BUY = "BID"
SIDE_SELL = "ASK"

# Rate Limit Type
REQUEST_WEIGHT = "REQUEST_WEIGHT"
ORDERS = "ORDERS"
ORDERS_24HR = "ORDERS_24HR"
RAW_REQUESTS = "RAW_REQUESTS"

# Rate Limit time intervals
ONE_MINUTE = 60
TEN_SECOND = 10
ONE_DAY = 86400

MAX_REQUEST = 5000

# Order States
ORDER_STATE = {
    "OPENING": OrderState.OPEN,
    "PENDING": OrderState.PARTIALLY_FILLED,
    "FILLED": OrderState.FILLED,
    "CANCELLED": OrderState.CANCELED,
    "FIRED": OrderState.FAILED,
    "REJECTED": OrderState.FAILED,
}

# Websocket event types
DIFF_EVENT_TYPE = "depthUpdate"
TRADE_EVENT_TYPE = "tradeUpdate"

RATE_LIMITS = [
    RateLimit(limit_id=PING_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=SERVER_TIME_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=EXCHANGE_INFO_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=TICKER_PRICE_CHANGE_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=TICKER_BOOK_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=SNAPSHOT_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=BIGONE_USER_STREAM_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=ACCOUNTS_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=SINGLE_ORDER, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=ORDER_LIST_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=CANCEL_ORDER, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=CANCEL_ORDER_BY_ID_OR_CLIENT, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=ORDER_BY_ID_OR_CLIENT, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=ORDER_PATH_URL, limit=500, time_interval=TEN_SECOND),
    RateLimit(limit_id=MY_TRADES_PATH_URL, limit=500, time_interval=TEN_SECOND),
]

ORDER_NOT_EXIST_ERROR_CODE = -2013
ORDER_NOT_EXIST_MESSAGE = "Order does not exist"
UNKNOWN_ORDER_ERROR_CODE = -2011
UNKNOWN_ORDER_MESSAGE = "Unknown order sent"
