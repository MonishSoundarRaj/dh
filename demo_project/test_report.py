import os
import unittest

from grades import average
from loader import load_scores
from report import build_report

ROSTER = os.path.join(os.path.dirname(__file__), "roster.csv")


class TestGradebook(unittest.TestCase):
    def test_average(self):
        self.assertAlmostEqual(average([90, 92.5, 87.5]), 90.0)

    def test_loads_every_student(self):
        self.assertEqual(list(load_scores(ROSTER)), ["Ada", "Linus", "Grace", "Alan"])

    def test_decimal_scores(self):
        self.assertEqual(load_scores(ROSTER)["Linus"], [90.0, 92.5, 87.5])

    def test_report(self):
        self.assertEqual(build_report(ROSTER), [
            "Ada: 91.7 (A)",
            "Linus: 90.0 (A)",
            "Grace: 80.0 (B)",
            "Alan: 65.2 (D)",
        ])


if __name__ == "__main__":
    unittest.main()
