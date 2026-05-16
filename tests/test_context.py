import json
import tempfile
import unittest
from pathlib import Path

from story_world.agents import DeterministicDemoAgent
from story_world.context import StoryContextBuilder
from story_world.collector import InformationCollector
from story_world.config import WorldGeneratorConfig
from story_world.generator import WorldGenerator
from story_world.story import StorySessionManager
from story_world.storage import WorldStore


class StoryContextTests(unittest.TestCase):
    def test_builder_reads_index_and_current_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            generator = WorldGenerator(
                agent=DeterministicDemoAgent(),
                runtime_root=Path(tmp),
            )
            world = generator.create_world("测试世界", world_id="demo-world")
            generator.initialize_context(
                world_id=world["world_id"],
                user_prompt="测试世界",
                history_path="2,5,3,3",
                space_path="2,1,1,1",
            )

            builder = StoryContextBuilder(runtime_root=Path(tmp))
            context = builder.build(
                world_id="demo-world",
                history_path="2,5,3,3",
                space_path="2,1,1,1",
            )

            self.assertEqual(context["current"]["history"]["status"], "full")
            self.assertEqual(context["current"]["space"]["status"], "full")
            self.assertGreaterEqual(context["index_summary"]["history_count"], 5)
            self.assertGreaterEqual(context["index_summary"]["space_count"], 5)
            self.assertTrue(context["nearby"]["history"])
            self.assertTrue(context["nearby"]["space"])
            self.assertIn("共享前缀越长", context["path_distance"]["rule"])
            self.assertTrue(context["path_distance"]["history"])

    def test_initial_history_events_are_saved_and_collected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorldGeneratorConfig()
            generator = WorldGenerator(
                agent=DeterministicDemoAgent(),
                config=config,
                runtime_root=Path(tmp),
            )
            world = generator.create_world("测试世界", world_id="event-world")
            generator.initialize_context(
                world_id=world["world_id"],
                user_prompt="测试世界",
                history_path="1,3,3,3",
                space_path="1,2,2,2",
            )

            store = WorldStore(Path(tmp), "event-world")
            events = store.load_events((1, 3, 3, 3))
            self.assertTrue(any(event.get("category") == "public" for event in events))
            self.assertTrue(any(event.get("category") == "personal" for event in events))

            collected = InformationCollector(config=config, runtime_root=Path(tmp)).collect(
                world_id="event-world",
                history_path="1,3,3,3",
                space_path="1,2,2,2",
            )
            self.assertTrue(collected["current_time_events"])
            self.assertTrue(collected["current_time_event_groups"]["public_events"])
            self.assertTrue(collected["current_time_event_groups"]["personal_events"])
            self.assertIn("共享前缀越长", collected["path_distance_rule"])

    def test_characters_are_snapshotted_to_spacetime_and_reusable_for_nearby_story(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = DeterministicDemoAgent()
            config = WorldGeneratorConfig()
            generator = WorldGenerator(agent=agent, config=config, runtime_root=Path(tmp))
            world = generator.create_world("人物复用世界", world_id="reuse-world")
            manager = StorySessionManager(agent=agent, config=config, runtime_root=Path(tmp))
            first = manager.start(
                world_id=world["world_id"],
                history_path="1,1,1,1",
                space_path="1,1,1,1",
                protagonist_prompt="第一位主角",
                generate_first_segment=False,
            )

            store = WorldStore(Path(tmp), "reuse-world")
            snapshot = store.list_spacetime_characters((1, 1, 1, 1), (1, 1, 1, 1))
            self.assertTrue(snapshot)
            self.assertTrue(any(item.get("role") == "other" for item in snapshot))

            second = manager.start(
                world_id=world["world_id"],
                history_path="1,1,1,2",
                space_path="1,1,1,2",
                protagonist_prompt="第二位主角",
                generate_first_segment=False,
            )
            reusable = second["collected_context"]["reusable_spacetime_characters"]
            self.assertTrue(reusable)
            self.assertEqual(reusable[0]["character"]["name"], "示例同伴")


if __name__ == "__main__":
    unittest.main()
