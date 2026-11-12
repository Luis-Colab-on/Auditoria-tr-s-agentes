import unittest
from hooks import submit


class HooksTest(unittest.TestCase):
    def test_regular(self):
        self.assertEqual(submit(['submit'], 10), 10)

    def test_joint_registration(self):
        self.assertEqual(submit(['submit', 'legacy_submit'], 10), 10)
