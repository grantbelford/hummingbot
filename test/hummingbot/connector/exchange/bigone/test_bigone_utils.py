import unittest
from datetime import datetime

from hummingbot.connector.exchange.bigone import bigone_utils as utils


class BigoneUtilTestCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.base_asset = "COINALPHA"
        cls.quote_asset = "HBOT"
        cls.trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.hb_trading_pair = f"{cls.base_asset}-{cls.quote_asset}"
        cls.ex_trading_pair = f"{cls.base_asset}-{cls.quote_asset}"

    def test_datetime_val_or_now(self):
        self.assertIsNone(utils.datetime_val_or_now('NotValidDate', '', False))
        self.assertLessEqual(datetime.now(), utils.datetime_val_or_now('NotValidDate', '', True))
        self.assertLessEqual(datetime.now(), utils.datetime_val_or_now('NotValidDate', ''))
        _now = '2023-04-19T18:53:17.981Z'
        _fNow = datetime.strptime(_now, '%Y-%m-%dT%H:%M:%S.%fZ')
        self.assertEqual(_fNow, utils.datetime_val_or_now(_now))

    def test_is_exchange_information_valid(self):
        invalid_info_1 = {
            "permissionSets": [["MARGIN"]],
        }

        self.assertFalse(utils.is_exchange_information_valid(invalid_info_1))

        invalid_info_2 = {
            "name": None,
        }

        self.assertFalse(utils.is_exchange_information_valid(invalid_info_2))

        invalid_info_3 = {
        }

        self.assertFalse(utils.is_exchange_information_valid(invalid_info_3))

        invalid_info_4 = {
            "name": "COINALPHA-HBOT",
        }

        self.assertTrue(utils.is_exchange_information_valid(invalid_info_4))
