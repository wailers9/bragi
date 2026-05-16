import tempfile
import unittest
from pathlib import Path

from story_world.agents import DeterministicDemoAgent
from story_world.generator import WorldGenerator


class SpacetimeStorageTests(unittest.TestCase):
    def test_world_initialization_uses_nested_time_scoped_space_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            generator = WorldGenerator(agent=DeterministicDemoAgent(), runtime_root=Path(tmp))
            world = generator.create_world("嵌套时空测试", world_id="nested-world")

            base = Path(tmp) / world["world_id"]
            self.assertTrue((base / "history" / "0.0.0.0" / "node.json").exists())
            self.assertTrue((base / "history" / "1.0.0.0" / "node.json").exists())
            self.assertTrue((base / "space" / "0.0.0.0" / "node.json").exists())
            self.assertTrue((base / "space" / "1.0.0.0" / "node.json").exists())

            generator.initialize_context(
                world_id=world["world_id"],
                user_prompt="嵌套时空测试",
                history_path="1,3,3,3",
                space_path="1,2,2,2",
            )

            time_leaf = (
                base
                / "history"
                / "1.0.0.0"
                / "1.3.0.0"
                / "1.3.3.0"
                / "1.3.3.3"
            )
            self.assertTrue((time_leaf / "node.json").exists())
            self.assertTrue(
                (
                    time_leaf
                    / "space"
                    / "1.0.0.0"
                    / "1.2.0.0"
                    / "1.2.2.0"
                    / "1.2.2.2"
                    / "node.json"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
