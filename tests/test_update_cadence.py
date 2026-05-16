import unittest
import tempfile
from pathlib import Path

from story_world.agents import DeterministicDemoAgent
from story_world.config import StoryConfig, WorldGeneratorConfig
from story_world.generator import WorldGenerator
from story_world.story import StorySessionManager
from story_world.storage import WorldStore


class FixedRandom:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def random(self) -> float:
        return self.values.pop(0)


class RecordingDemoAgent(DeterministicDemoAgent):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_json(self, prompt: str, *, schema_name: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        return super().generate_json(prompt, schema_name=schema_name, schema=schema)


class UpdateCadenceTests(unittest.TestCase):
    def test_probability_uses_turns_since_update(self) -> None:
        manager = StorySessionManager(
            agent=DeterministicDemoAgent(),
            config=WorldGeneratorConfig(),
        )
        self.assertAlmostEqual(manager._update_probability(0), 0.05)
        self.assertAlmostEqual(manager._update_probability(5), 0.45)

    def test_time_and_space_update_are_independent(self) -> None:
        config = WorldGeneratorConfig(
            story=StoryConfig(
                update_cadences={
                    "normal": {
                        "base_probability": 0.05,
                        "growth_per_turn": 0.08,
                        "max_probability": 0.65,
                    }
                }
            )
        )
        manager = StorySessionManager(agent=DeterministicDemoAgent(), config=config)
        session = {
            "session_id": "test",
            "history_path": [2, 5, 3, 3],
            "space_path": [2, 1, 1, 1],
            "turns_since_time_update": 5,
            "turns_since_space_update": 5,
        }
        old_history = tuple(session["history_path"])
        old_space = tuple(session["space_path"])
        time_probability = manager._update_probability(session["turns_since_time_update"])
        space_probability = manager._update_probability(session["turns_since_space_update"])
        rng = FixedRandom([0.1, 0.9])
        new_history = manager._maybe_advance_time(old_history, time_probability, rng)
        new_space = manager._maybe_move_space(old_space, space_probability, rng)
        if new_history != old_history:
            session["turns_since_time_update"] = 0
        if new_space != old_space:
            session["turns_since_space_update"] = 0

        self.assertEqual(new_history, (2, 5, 3, 4))
        self.assertEqual(new_space, old_space)
        self.assertEqual(session["turns_since_time_update"], 0)
        self.assertEqual(session["turns_since_space_update"], 5)

    def test_changed_spacetime_is_initialized_and_reported_to_story_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorldGeneratorConfig(
                story=StoryConfig(
                    debug_story_agent_input=True,
                    update_cadences={
                        "normal": {
                            "base_probability": 1.0,
                            "growth_per_turn": 0.0,
                            "max_probability": 1.0,
                        }
                    },
                )
            )
            agent = RecordingDemoAgent()
            generator = WorldGenerator(agent=agent, config=config, runtime_root=Path(tmp))
            world = generator.create_world("强制时空更新测试", world_id="update-world")
            generator.initialize_context(
                world_id=world["world_id"],
                user_prompt="强制时空更新测试",
                history_path="1,3,3,3",
                space_path="1,2,2,2",
                protagonist_prompt="测试主角",
            )

            manager = StorySessionManager(agent=agent, config=config, runtime_root=Path(tmp))
            first = manager.start(
                world_id=world["world_id"],
                history_path="1,3,3,3",
                space_path="1,2,2,2",
                protagonist_prompt="测试主角",
                session_id="forced-update",
            )
            second = manager.submit_choice(session_id=first["session"]["session_id"], choice_id="A")

            notes = second["collected_context"]["manager_notes"]
            self.assertTrue(notes["time_or_space_changed"])
            self.assertIn("重要状态变化", notes["critical_story_notice"])
            self.assertNotEqual(notes["previous_history_path"], notes["current_history_path"])
            self.assertNotEqual(notes["previous_space_path"], notes["current_space_path"])

            store = WorldStore(Path(tmp), world["world_id"])
            new_history = tuple(second["session"]["history_path"])
            new_space = tuple(second["session"]["space_path"])
            self.assertEqual(store.load_history_node(new_history)["status"], "full")
            self.assertEqual(store.load_space_node_at_time(new_history, new_space)["status"], "full")
            self.assertEqual(tuple(second["collected_context"]["current_paths"]["history_path"]), new_history)
            self.assertEqual(tuple(second["collected_context"]["current_paths"]["space_path"]), new_space)
            self.assertTrue(second["collected_context"]["current_time_events"])
            self.assertEqual(second["collected_context"]["interaction_count"], second["session"]["interaction_count"])

            prompt = (Path(tmp) / world["world_id"] / "debug" / "story_agent_input_turn_0001.txt").read_text(
                encoding="utf-8"
            )
            self.assertIn("critical_story_notice", prompt)
            self.assertIn("不得继续把角色写在 previous_history_path", prompt)
            self.assertIn("path_distance_rule", prompt)
            self.assertIn("共享前缀越长", prompt)

    def test_character_roster_changes_are_probabilistic_and_reported_to_story_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WorldGeneratorConfig(
                story=StoryConfig(
                    debug_story_agent_input=True,
                    update_cadences={
                        "normal": {
                            "base_probability": 0.0,
                            "growth_per_turn": 0.0,
                            "max_probability": 0.0,
                        }
                    },
                    character_departure_probability=1.0,
                    character_departure_relationship_weight=0.0,
                    character_arrival_probability=1.0,
                    character_extra_arrival_probability=0.0,
                    character_max_new_arrivals=2,
                )
            )
            agent = RecordingDemoAgent()
            generator = WorldGenerator(agent=agent, config=config, runtime_root=Path(tmp))
            world = generator.create_world("强制人物变化测试", world_id="character-update-world")
            generator.initialize_context(
                world_id=world["world_id"],
                user_prompt="强制人物变化测试",
                history_path="1,3,3,3",
                space_path="1,2,2,2",
                protagonist_prompt="测试主角",
            )

            manager = StorySessionManager(agent=agent, config=config, runtime_root=Path(tmp))
            first = manager.start(
                world_id=world["world_id"],
                history_path="1,3,3,3",
                space_path="1,2,2,2",
                protagonist_prompt="测试主角",
                session_id="forced-character-update",
            )
            second = manager.submit_choice(session_id=first["session"]["session_id"], choice_id="A")

            notes = second["collected_context"]["manager_notes"]
            self.assertTrue(notes["character_roster_changed"])
            self.assertTrue(notes["departed_characters"])
            self.assertTrue(notes["joined_characters"])
            self.assertIn("重要人物变化", notes["critical_character_notice"])
            self.assertNotIn("companion_1", notes["active_characters"])
            self.assertTrue(any(item.startswith("other_new_") for item in notes["active_characters"]))
            self.assertTrue(any(item["id"].startswith("other_new_") for item in second["collected_context"]["other_characters"]))

            prompt = (
                Path(tmp)
                / world["world_id"]
                / "debug"
                / "story_agent_input_turn_0001.txt"
            ).read_text(encoding="utf-8")
            self.assertIn("critical_character_notice", prompt)
            self.assertIn("必须解释 departed_characters", prompt)
            addition_prompts = [item for item in agent.prompts if "故事人物加入 Agent" in item]
            self.assertTrue(addition_prompts)
            self.assertIn("recent_story_state", addition_prompts[-1])
            self.assertIn("latest_choice", addition_prompts[-1])
            self.assertIn("current_time_events", addition_prompts[-1])
            self.assertIn("departed_characters_this_turn", addition_prompts[-1])


if __name__ == "__main__":
    unittest.main()
