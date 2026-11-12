import unittest
from app import balance_after_payment, checkout


class Contract(unittest.TestCase):
    def test_refund_increases_balance(self):
        self.assertEqual(balance_after_payment(100, -20), 120)

    def test_checkout_protects_internal_helper(self):
        with self.assertRaises(ValueError):
            checkout(-10)
        self.assertEqual(checkout(100), 90)
