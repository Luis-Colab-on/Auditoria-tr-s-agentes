"""Controller-owned reproduction; run only through the isolated executor."""
import unittest
from app import balance_after_payment


class RefundContract(unittest.TestCase):
    def test_refund_twenty(self):
        self.assertEqual(balance_after_payment(100, -20), 120)

    def test_refund_thirty_five(self):
        self.assertEqual(balance_after_payment(250, -35), 285)

    def test_payment_twenty(self):
        self.assertEqual(balance_after_payment(100, 20), 80)

    def test_payment_thirty_five(self):
        self.assertEqual(balance_after_payment(250, 35), 215)


if __name__ == '__main__':
    unittest.main(verbosity=2)
