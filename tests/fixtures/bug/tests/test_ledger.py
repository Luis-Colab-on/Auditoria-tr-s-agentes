import unittest
from ledger import refund


class RefundTest(unittest.TestCase):
    def test_sixteen_amounts_one_mechanism(self):
        for amount in range(1, 17):
            with self.subTest(amount=amount):
                self.assertEqual(refund(100, amount), 100 - amount)
