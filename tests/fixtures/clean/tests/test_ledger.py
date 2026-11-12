import unittest
from ledger import refund


class RefundTest(unittest.TestCase):
    def test_refund(self):
        self.assertEqual(refund(100, 10), 90)

    def test_negative_is_rejected(self):
        with self.assertRaises(ValueError):
            refund(100, -1)
