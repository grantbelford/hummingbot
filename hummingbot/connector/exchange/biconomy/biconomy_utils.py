from decimal import Decimal
from typing import Dict

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData
from hummingbot.core.data_type.trade_fee import TradeFeeSchema

CENTRALIZED = True
EXAMPLE_PAIR = "ZRX-ETH"

DEFAULT_FEES = TradeFeeSchema(
    maker_percent_fee_decimal=Decimal("0.02"),
    taker_percent_fee_decimal=Decimal("0.02"),
    buy_percent_fee_deducted_from_returns=True
)


def is_exchange_information_valid(exchange_info: list[Dict]) -> bool:
    """
    Verifies if a trading pair is enabled to operate with based on its exchange information
    :param exchange_info: the exchange information for a trading pair
    :return: True if the trading pair is enabled, False otherwise
    """
    return exchange_info.get("status", None) == "trading"


class BiconomyConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="biconomy", const=True, client_data=None)
    biconomy_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Biconomy API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )
    biconomy_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your Biconomy API secret",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )

    class Config:
        title = "biconomy"


KEYS = BiconomyConfigMap.construct()

# OTHER_DOMAINS = ["biconomy_us"]
# OTHER_DOMAINS_PARAMETER = {"biconomy_us": "us"}
# OTHER_DOMAINS_EXAMPLE_PAIR = {"biconomy_us": "BTC-USDT"}
# OTHER_DOMAINS_DEFAULT_FEES = {"biconomy_us": DEFAULT_FEES}


# class BiconomyUSConfigMap(BaseConnectorConfigMap):
#     connector: str = Field(default="biconomy_us",
#                            const=True, client_data=None)
#     biconomy_api_key: SecretStr = Field(
#         default=...,
#         client_data=ClientFieldData(
#             prompt=lambda cm: "Enter your Biconomy US API key",
#             is_secure=True,
#             is_connect_key=True,
#             prompt_on_new=True,
#         )
#     )
#     biconomy_api_secret: SecretStr = Field(
#         default=...,
#         client_data=ClientFieldData(
#             prompt=lambda cm: "Enter your Biconomy US API secret",
#             is_secure=True,
#             is_connect_key=True,
#             prompt_on_new=True,
#         )
#     )

#     class Config:
#         title = "biconomy_us"


# OTHER_DOMAINS_KEYS = {"biconomy_us": BiconomyUSConfigMap.construct()}