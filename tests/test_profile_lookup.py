import unittest

from profile_lookup import normalize_profile_text, profile_match_score, select_best_profile


class TestProfileLookup(unittest.TestCase):
    def setUp(self):
        self.profiles = [
            {'title': 'GPT: Lovely Lots Drop'},
            {'title': 'People Possession, Arcadia'},
            {'title': 'Medium Roast'},
        ]

    def test_normalize_profile_text(self):
        self.assertEqual(normalize_profile_text('GPT: Lovely Lots Drop'), 'gptlovelylotsdrop')

    def test_profile_match_score(self):
        self.assertGreater(profile_match_score('lovelylots', 'GPT: Lovely Lots Drop'), 0.6)

    def test_select_best_profile(self):
        profile = select_best_profile(self.profiles, 'lovelylots')
        self.assertEqual(profile['title'], 'GPT: Lovely Lots Drop')


if __name__ == '__main__':
    unittest.main()