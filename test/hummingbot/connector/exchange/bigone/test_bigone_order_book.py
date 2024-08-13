import time
from unittest import TestCase

from hummingbot.connector.exchange.bigone.bigone_order_book import BigoneOrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessageType


class BigoneOrderBookTests(TestCase):

    def test_snapshot_message_from_exchange(self):
        snapshot_message = BigoneOrderBook.snapshot_message_from_exchange(
            msg={
                "data": {
                    "asset_pair_name": "COINALPHA-HBOT",
                    "bids": [
                        {
                            "price": "4.00000000",
                            "order_count": 4,
                            "quantity": "431.00000000"
                        }
                    ],
                    "asks": [
                        {
                            "price": "4.00000200",
                            "order_count": 2,
                            "quantity": "12.00000000"
                        }
                    ]
                }
            },
            timestamp=1640000000.0,
            metadata={"trading_pair": "COINALPHA-HBOT"}
        )

        self.assertEqual("COINALPHA-HBOT", snapshot_message.trading_pair)
        self.assertEqual(OrderBookMessageType.SNAPSHOT, snapshot_message.type)
        self.assertEqual(1640000000.0, snapshot_message.timestamp)
        self.assertEqual(1640000000.0, snapshot_message.update_id)
        self.assertEqual(-1, snapshot_message.trade_id)
        self.assertEqual(1, len(snapshot_message.bids))
        self.assertEqual(4.0, snapshot_message.bids[0].price)
        self.assertEqual(431.0, snapshot_message.bids[0].amount)
        self.assertEqual(1640000000.0, snapshot_message.bids[0].update_id)
        self.assertEqual(1, len(snapshot_message.asks))
        self.assertEqual(4.000002, snapshot_message.asks[0].price)
        self.assertEqual(12.0, snapshot_message.asks[0].amount)
        self.assertEqual(1640000000.0, snapshot_message.asks[0].update_id)

    def test_diff_message_from_exchange(self):
        diff_msg = BigoneOrderBook.diff_message_from_exchange(
            msg= {
                "requestId": "1",
                "depthUpdate": {
                    "depth": {
                        "market": "COINALPHA-HBOT",
                        "asks": [
                            {
                                "price": "0.0026",
                                "order_count": 4,
                                "amount": "100"
                            }
                        ],
                        "bids": [
                            {
                                "price": "0.0024",
                                "order_count": 2,
                                "amount": "10"
                            }
                        ]
                    },
                    "changeId": "2",
                    "prevId": "1"
                }
            },
            timestamp=1640000000.0,
            metadata={"trading_pair": "COINALPHA-HBOT"}
        )

        self.assertEqual("COINALPHA-HBOT", diff_msg.trading_pair)
        self.assertEqual(OrderBookMessageType.DIFF, diff_msg.type)
        self.assertEqual(1640000000.0, diff_msg.timestamp)
        self.assertEqual(2, diff_msg.update_id)
        self.assertEqual(1, diff_msg.first_update_id)
        self.assertEqual(-1, diff_msg.trade_id)
        self.assertEqual(1, len(diff_msg.bids))
        self.assertEqual(0.0024, diff_msg.bids[0].price)
        self.assertEqual(10.0, diff_msg.bids[0].amount)
        self.assertEqual(2, diff_msg.bids[0].update_id)
        self.assertEqual(1, len(diff_msg.asks))
        self.assertEqual(0.0026, diff_msg.asks[0].price)
        self.assertEqual(100.0, diff_msg.asks[0].amount)
        self.assertEqual(2, diff_msg.asks[0].update_id)

    def test_trade_message_from_exchange(self):
        trade_update = {
            "requestId": "1",
            "tradeUpdate": {
                "trade": {
                    "id": "28622",
                    "price": "9.0",
                    "amount": "10000.0",
                    "market": "COINALPHA-HBOT",
                    "createdAt": "2018-09-12T09:52:37Z",
                    "makerOrder": None,
                    "takerOrder": {
                        "id": "",
                        "price": "",
                        "stopPrice": "",
                        "amount": "",
                        "market": "",
                        "side": "BID",
                        "state": "PENDING",
                        "filledAmount": "",
                        "filledFees": "",
                        "avgDealPrice": "",
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

        trade_message = BigoneOrderBook.trade_message_from_exchange(
            msg=trade_update,
            metadata={"trading_pair": "COINALPHA-HBOT"}
        )

        self.assertEqual("COINALPHA-HBOT", trade_message.trading_pair)
        self.assertEqual(OrderBookMessageType.TRADE, trade_message.type)
        self.assertEqual(int(time.time()), trade_message.timestamp)
        self.assertEqual(-1, trade_message.update_id)
        self.assertEqual(-1, trade_message.first_update_id)
        self.assertEqual("28622", trade_message.trade_id)
