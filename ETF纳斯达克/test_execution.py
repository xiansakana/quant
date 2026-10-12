"""离线执行安全性测试；不模拟行情收益，不替代聚宽回测。"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS, ModuleType
import sys
import unittest

sys.modules.setdefault('jqdata', ModuleType('jqdata'))
spec = importlib.util.spec_from_file_location('strategy', Path(__file__).with_name('nasdaq_etf_rotation.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        s.g = NS(target='NEW', cash_reserve=0.01, order_count=0)
        s.LimitOrderStyle = lambda p: p
        self.orders = []
        s.order = lambda code, amount, style: self.orders.append((code, amount, style)) or NS()
        self.context = NS(portfolio=NS(positions={}, available_cash=100000, total_value=100000))

    def test_partial_sale_does_not_buy_with_sale_proceeds_early(self):
        self.context.portfolio.positions = {'OLD': NS(total_amount=50000, closeable_amount=30000)}
        s.execute_target(self.context, {'OLD': 2.0, 'NEW': 1.0}, {'OLD': 10000, 'NEW': 50000})
        self.assertEqual([o[0] for o in self.orders], ['OLD'])
        self.assertEqual(self.orders[0][1], -10000)

    def test_uncloseable_old_position_blocks_new_buy(self):
        self.context.portfolio.positions = {'OLD': NS(total_amount=50000, closeable_amount=0)}
        s.execute_target(self.context, {'OLD': 2.0, 'NEW': 1.0}, {'OLD': 10000, 'NEW': 50000})
        self.assertEqual(self.orders, [])

    def test_cash_and_commission_reserve(self):
        s.execute_target(self.context, {'NEW': 1.0}, {'NEW': 200000})
        code, amount, price = self.orders[0]
        self.assertEqual(code, 'NEW')
        self.assertEqual(amount % 100, 0)
        self.assertLessEqual(amount*price*1.00025 + 10, 99000)

    def test_missing_quote_blocks_buy(self):
        s.execute_target(self.context, {}, {})
        self.assertEqual(self.orders, [])

    def test_split_odd_lot_does_not_block_rotation_forever(self):
        self.context.portfolio.positions = {'OLD': NS(total_amount=14, closeable_amount=14)}
        s.execute_target(self.context, {'OLD': 2, 'NEW': 1}, {'OLD': 10000, 'NEW': 10000})
        self.assertEqual(self.orders, [('OLD', -14, 1.997)])

    def test_risk_off_only_sells(self):
        s.g.target = None
        self.context.portfolio.positions = {'OLD': NS(total_amount=10000, closeable_amount=10000)}
        s.execute_target(self.context, {'OLD': 2}, {'OLD': 20000})
        self.assertEqual(self.orders, [('OLD', -10000, 1.997)])


if __name__ == '__main__':
    unittest.main()
