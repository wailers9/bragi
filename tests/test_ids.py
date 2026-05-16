import unittest

from story_world.ids import expand_neighbor_paths, parse_path, paths_from_manual_ranges


class IdTests(unittest.TestCase):
    def test_parse_path(self) -> None:
        self.assertEqual(parse_path("2,5,3,3"), (2, 5, 3, 3))
        self.assertEqual(parse_path("2.5.3.3"), (2, 5, 3, 3))

    def test_expand_neighbor_paths(self) -> None:
        paths = expand_neighbor_paths((2, 1, 1, 1), [0, 1, 1, 2], 3)
        self.assertIn((2, 1, 1, 1), paths)
        self.assertIn((2, 2, 1, 1), paths)
        self.assertIn((2, 1, 2, 1), paths)
        self.assertIn((2, 1, 1, 3), paths)

    def test_manual_ranges(self) -> None:
        paths = paths_from_manual_ranges({2: (2, 4)}, (2, 5, 3, 3), 5)
        self.assertIn((2, 5, 2, 3), paths)
        self.assertIn((2, 5, 4, 3), paths)
        self.assertIn((2, 5, 3, 3), paths)


if __name__ == "__main__":
    unittest.main()
