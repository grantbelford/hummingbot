from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData
from hummingbot.core.data_type.trade_fee import TradeFeeSchema

CENTRALIZED = True
EXAMPLE_PAIR = "ZRX-ETH"

DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0.002"),
    taker_percent_fee_decimal=Decimal("0.002"),
    buy_percent_fee_deducted_from_returns=True
)


def trading_fees(self):
    pass


def datetime_val_or_now(string_value: str,
                        string_format: str = '%Y-%m-%dT%H:%M:%S.%fZ',
                        on_error_return_now: bool = True,
                        ) -> datetime:
    try:
        return datetime.strptime(string_value, string_format)
    except Exception:
        if on_error_return_now:
            return datetime.now()
        else:
            return None


def is_exchange_information_valid(exchange_info: Dict[str, Any]) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its exchange information
    :param exchange_info: the exchange information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    is_trading = False
    if isinstance(exchange_info, dict):
        if exchange_info.get("name") is not None:
            is_trading = True
        return is_trading


class BigoneConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="bigone", const=True, client_data=None)
    bigone_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Bigone API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )
    bigone_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Bigone API secret",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )

    class Config:
        title = "bigone"


KEYS = BigoneConfigMap.construct()
