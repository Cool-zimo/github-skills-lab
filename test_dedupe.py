import unittest

from dedupe import unique_sorted


class UniqueSortedTest(unittest.TestCase):
    def test_removes_duplicates_and_sorts(self):
        self.assertEqual(unique_sorted(["b", "a", "b"]), ["a", "b"])

    def test_empty(self):
        self.assertEqual(unique_sorted([]), [])

    def test_does_not_mutate_input(self):
        items = ["c", "a", "c"]
        unique_sorted(items)
        self.assertEqual(items, ["c", "a", "c"])


if __name__ == "__main__":
    unittest.main()
