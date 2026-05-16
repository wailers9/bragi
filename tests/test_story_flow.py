import tempfile
import unittest
from pathlib import Path

from story_world.agents import DeterministicDemoAgent, _parse_agent_json
from story_world.config import AgentConfig, StoryConfig, WorldGeneratorConfig
from story_world.generator import WorldGenerator
from story_world.storage import WorldStore
from story_world.story import StorySessionManager
from story_world.web import StoryWorldWebHandler


class StoryFlowTests(unittest.TestCase):
    def test_agent_json_parser_accepts_raw_newlines_inside_strings(self) -> None:
        payload = '{"story": "第一行\n第二行", "choices": [], "new_events": [], "state_notes": "ok"}'
        parsed = _parse_agent_json(payload, provider="deepseek")
        self.assertEqual(parsed["story"], "第一行\n第二行")

    def test_web_agent_selection_prefers_deepseek_model_over_stale_agent_field(self) -> None:
        handler = StoryWorldWebHandler.__new__(StoryWorldWebHandler)
        config = WorldGeneratorConfig(agent=AgentConfig(default_agent="openai", model="gpt-5.5"))

        selected, model = handler._agent_selection(
            {"agent": "openai", "model": "deepseek-chat"},
            config,
            default_agent="openai",
            default_model="gpt-5.5",
        )
        self.assertEqual(selected, "deepseek")
        self.assertEqual(model, "deepseek-chat")

        selected, model = handler._agent_selection(
            {},
            config,
            default_agent="deepseek",
            default_model="deepseek-chat",
        )
        self.assertEqual(selected, "deepseek")
        self.assertEqual(model, "deepseek-chat")

    def test_session_agent_selection_overrides_stale_followup_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handler = StoryWorldWebHandler.__new__(StoryWorldWebHandler)
            config = WorldGeneratorConfig()
            config.runtime.worlds_root = tmp
            store = WorldStore(Path(tmp), "agent-world")
            store.save_manifest(
                {
                    "world_id": "agent-world",
                    "prompt": "测试世界",
                    "config": config.to_dict(),
                    "bootstrap": {},
                }
            )
            store.save_session(
                "session-1",
                {
                    "session_id": "session-1",
                    "world_id": "agent-world",
                    "agent_selection": {"agent": "deepseek", "model": "deepseek-chat"},
                },
            )

            payload = handler._agent_payload_for_session(
                "session-1",
                {"agent": "openai", "model": "gpt-5.5"},
                config,
            )
            self.assertEqual(payload["agent"], "deepseek")
            self.assertEqual(payload["model"], "deepseek-chat")

        selected, model = handler._agent_selection(
            {"agent": "deepseek", "model": "gpt-5.5"},
            config,
            default_agent="openai",
            default_model="gpt-5.5",
        )
        self.assertEqual(selected, "deepseek")
        self.assertEqual(model, "deepseek-chat")

    def test_story_session_initializes_characters_and_continues_after_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = DeterministicDemoAgent()
            config = WorldGeneratorConfig()
            generator = WorldGenerator(agent=agent, config=config, runtime_root=Path(tmp))
            world = generator.create_world("测试故事世界", world_id="story-world")
            generator.initialize_context(
                world_id=world["world_id"],
                user_prompt="测试故事世界",
                history_path="2,5,3,3",
                space_path="2,1,1,1",
                protagonist_prompt="一个谨慎但好奇的主角",
            )
            self.assertTrue((Path(tmp) / "story-world" / "characters" / "protagonist.json").exists())

            manager = StorySessionManager(agent=agent, config=config, runtime_root=Path(tmp))
            first = manager.start(
                world_id="story-world",
                history_path="2,5,3,3",
                space_path="2,1,1,1",
                protagonist_prompt="一个谨慎但好奇的主角",
            )
            self.assertEqual(first["output"]["choices"], [])
            self.assertTrue(first["intro"]["intro"])
            self.assertTrue(first["intro"]["mysteries"])
            self.assertTrue(first["collected_context"]["protagonist"])
            self.assertTrue(first["collected_context"]["story_phase"]["is_story_start"])
            self.assertEqual(first["collected_context"]["story_phase"]["phase"], "opening")

            session_id = first["session"]["session_id"]
            second = manager.submit_choice(session_id=session_id, choice_text="调查异常")
            self.assertEqual(second["output"]["choices"], [])
            self.assertGreaterEqual(second["session"]["interaction_count"], 1)
            self.assertTrue(second["collected_context"]["all_event_summary"])
            self.assertTrue(second["collected_context"]["story_history"]["recent_full_segments"])
            self.assertEqual(second["session"]["choices"][-1]["text"], "调查异常")
            self.assertFalse(second["collected_context"]["story_phase"]["is_story_start"])
            self.assertEqual(second["collected_context"]["story_phase"]["phase"], "continuation")

    def test_story_ending_is_loaded_as_visible_story_text_with_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = DeterministicDemoAgent()
            config = WorldGeneratorConfig(
                story=StoryConfig(
                    story_length_mode="normal",
                    ending_modes={"normal": {"after_interactions": 0, "probability": 1.0}},
                )
            )
            generator = WorldGenerator(agent=agent, config=config, runtime_root=Path(tmp))
            world = generator.create_world("结尾测试世界", world_id="ending-world")
            manager = StorySessionManager(agent=agent, config=config, runtime_root=Path(tmp))
            first = manager.start(
                world_id=world["world_id"],
                history_path="1,1,1,1",
                space_path="1,1,1,1",
                protagonist_prompt="一个需要完成任务的主角",
            )

            ended = manager.submit_choice(session_id=first["session"]["session_id"], choice_text="收束故事")
            self.assertTrue(ended["session"]["ended"])
            self.assertIn(ended["collected_context"]["manager_notes"]["ending_outcome"], {"good", "bad"})
            loaded = manager.load(session_id=first["session"]["session_id"])
            self.assertEqual(loaded["ending"]["ending"], ended["ending"]["ending"])
            handler = StoryWorldWebHandler.__new__(StoryWorldWebHandler)
            full_text = handler._full_story_text(loaded["session"])
            self.assertIn(loaded["session"]["story_outputs"][0]["story"], full_text)
            self.assertIn(loaded["ending"]["ending"], full_text)

    def test_second_story_marks_known_world_scope_and_random_spacetime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            agent = DeterministicDemoAgent()
            config = WorldGeneratorConfig()
            generator = WorldGenerator(agent=agent, config=config, runtime_root=Path(tmp))
            world = generator.create_world("已知世界测试", world_id="known-world")
            manager = StorySessionManager(agent=agent, config=config, runtime_root=Path(tmp))
            first = manager.start(
                world_id=world["world_id"],
                history_path="1,1,1,1",
                space_path="1,1,1,1",
                protagonist_prompt="第一位主角",
            )
            second = manager.start(
                world_id=world["world_id"],
                history_path="2,2,2,2",
                space_path="2,1,2,1",
                protagonist_prompt="第二位主角",
            )

            self.assertEqual(first["session"]["story_number"], 1)
            self.assertEqual(second["session"]["story_number"], 2)
            self.assertTrue(second["session"]["known_world_new_story"])
            self.assertTrue(second["collected_context"]["manager_notes"]["known_world_new_story"])
            self.assertIn("已知世界的新故事", second["collected_context"]["key_facts"]["story_scope"])
            self.assertEqual(second["session"]["history_path"], [2, 2, 2, 2])
            self.assertEqual(second["session"]["space_path"], [2, 1, 2, 1])


if __name__ == "__main__":
    unittest.main()
