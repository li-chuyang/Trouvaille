import unittest

from stats import mean


class MeanTests(unittest.TestCase):
    def test_even_average(self) -> None:
        self.assertEqual(mean([2, 4]), 3.0)

    def test_empty_rejected(self) -> None:
        with self.assertRaises(ValueError):
            mean([])


if __name__ == "__main__":
    unittest.main()
