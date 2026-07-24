import unittest

from brew_recommendation import (
    build_brew_recommendation,
    estimate_dose_grams,
    recommend_basket,
    recommend_ode_gen2_setting,
)


class TestCreateScheduleHelpers(unittest.TestCase):
    def test_estimate_dose_grams(self):
        self.assertEqual(estimate_dose_grams(180, 16), 11.2)

    def test_recommend_ode_gen2_setting(self):
        self.assertEqual(recommend_ode_gen2_setting(16), "5.5")
        self.assertEqual(recommend_ode_gen2_setting(17.5), "6.5")

    def test_recommend_basket(self):
        self.assertEqual(recommend_basket(11.2), "1-cup / small single-serve basket")
        self.assertEqual(recommend_basket(18.0), "2-cup basket")

    def test_build_brew_recommendation(self):
        recommendation = build_brew_recommendation(180, 16)
        self.assertEqual(recommendation["dose_grams"], 11.2)
        self.assertEqual(recommendation["ode_gen2_setting"], "5.5")
        self.assertEqual(recommendation["basket"], "1-cup / small single-serve basket")


if __name__ == "__main__":
    unittest.main()