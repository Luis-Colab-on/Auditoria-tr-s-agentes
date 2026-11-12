import unittest
from api import handle


class GuardTest(unittest.TestCase):
    def test_guard_in_other_layer(self):
        self.assertEqual(handle({'numerator': 10, 'denominator': 0})[1], 400)

    def test_normal_case(self):
        self.assertEqual(handle({'numerator': 10, 'denominator': 2}), ({'value': 5}, 200))
