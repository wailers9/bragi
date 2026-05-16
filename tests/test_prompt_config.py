import unittest

from story_world.config import WorldGeneratorConfig, WorldGenerationConfig
from story_world.agents import DeterministicDemoAgent
from story_world.prompts import (
    history_init_prompt,
    intro_prompt,
    space_init_prompt,
    story_create_prompt,
    story_ending_prompt,
    world_prompt,
)
from story_world.schemas import WORLD_SCHEMA


class PromptConfigTests(unittest.TestCase):
    def test_world_prompt_includes_personal_requirements(self) -> None:
        config = WorldGeneratorConfig(
            world_generation=WorldGenerationConfig(personal_requirements="强调海洋文明")
        )
        prompt = world_prompt("架空世界", config)
        self.assertIn("强调海洋文明", prompt)
        self.assertIn("world_rules 必须是底层规则", prompt)
        self.assertIn("不要把表层风俗", prompt)
        self.assertIn("每条只能写一句话", prompt)
        self.assertIn("world_rules 最多 3 条", prompt)
        self.assertIn("其它未列出的自然规律、社会常识和人物行为默认符合现实", prompt)
        self.assertIn("不要默认落入矿区、矿石能源", prompt)
        self.assertIn("矿区、矿石能源、雾海、雾城、晶体", prompt)
        self.assertIn("不要把世界核心建立在“矿、雾、晶”", prompt)

    def test_story_prompt_includes_generation_requirements(self) -> None:
        prompt = story_create_prompt({}, [], "冷静、克制、不要出现第一人称", 1000)
        self.assertIn("冷静、克制、不要出现第一人称", prompt)
        self.assertIn("不少于 1000", prompt)
        self.assertIn("环境描写最多占 story 的 20%", prompt)
        self.assertIn("第一句必须从人物动作", prompt)
        self.assertIn("path_distance_rule", prompt)
        self.assertIn("不要替用户列出选项", prompt)
        self.assertIn('"choices": []', prompt)
        self.assertIn("故事要有宏大感", prompt)
        self.assertIn("个人行动能牵连时代变化", prompt)
        self.assertIn("key_facts", prompt)
        self.assertIn("已知世界的新故事", prompt)
        self.assertIn("矿井/矿脉异常、雾气逼近、晶体失控", prompt)

    def test_default_generation_requirements_match_requested_style(self) -> None:
        config = WorldGeneratorConfig()
        self.assertEqual("随机创作风格。", config.story.generation_requirements)
        self.assertIn("富有想象力", config.world_generation.personal_requirements)
        self.assertIn("最多三条", config.world_generation.personal_requirements)

    def test_intro_prompt_keeps_world_clear_and_mysterious(self) -> None:
        prompt = intro_prompt({"world_foundation": {"world_overview": "测试世界"}}, "简单生动")
        self.assertIn("让读者大概了解这个世界", prompt)
        self.assertIn("保留神秘感", prompt)
        self.assertIn("known_world", prompt)
        self.assertIn("mysteries", prompt)
        self.assertIn("共享前缀越长", prompt)
        self.assertIn("不要在引子里新增 context_json 中没有出现的人名", prompt)
        self.assertIn("intro_variation", prompt)
        self.assertIn("不要总用“某历某年/某某时代”开头", prompt)
        self.assertIn("不要按固定顺序写", prompt)
        self.assertIn("小孩子也能读懂", prompt)

    def test_story_writing_prompts_require_child_readable_language(self) -> None:
        story_prompt = story_create_prompt({}, [], "简单生动", 1000)
        ending_prompt = story_ending_prompt({}, [], {}, "简单生动")
        self.assertIn("小孩子也能读懂", story_prompt)
        self.assertIn("必要术语第一次出现时用短句解释", story_prompt)
        self.assertIn("小孩子也能读懂", ending_prompt)

    def test_world_prompt_explains_path_templates(self) -> None:
        prompt = world_prompt("架空世界", WorldGeneratorConfig())
        self.assertIn("[1,0,0,0]", prompt)
        self.assertIn("空间层级", prompt)
        self.assertIn("时间层级", prompt)

    def test_demo_agent_classifies_world_prompt_as_world_agent(self) -> None:
        result = DeterministicDemoAgent().generate_json(
            world_prompt("架空世界", WorldGeneratorConfig()),
            schema_name="world_bootstrap",
            schema=WORLD_SCHEMA,
        )
        self.assertIn("world_overview", result)
        self.assertNotIn("nodes", result)

    def test_init_prompts_include_relationship_context_and_null_rules(self) -> None:
        config = WorldGeneratorConfig()
        foundation = {
            "world_overview": "测试世界",
            "world_rules": ["只有世界生成时定义的规则可以作为底层规则。"],
        }
        history_prompt = history_init_prompt(
            "架空世界",
            foundation,
            [(1, 3, 3, 3)],
            (1, 3, 3, 3),
            config,
            {"ancestor_paths": [[1, 0, 0, 0]]},
        )
        space_prompt = space_init_prompt(
            "架空世界",
            foundation,
            [(1, 2, 2, 2)],
            (1, 2, 2, 2),
            config,
            {"current_history_path": [1, 3, 3, 3]},
        )
        self.assertIn("ancestor_paths", history_prompt)
        self.assertIn("detail 与 ongoing_events 可以为 null", history_prompt)
        self.assertIn("编号距离含义", history_prompt)
        self.assertIn("current_history_path", space_prompt)
        self.assertIn("可以为 null", space_prompt)
        self.assertIn("编号距离含义", space_prompt)
        self.assertIn("不能为当前地点创造新的物理法则", space_prompt)
        self.assertIn("不能为当前时代创造新的底层法则", history_prompt)
        self.assertIn("world_foundation.world_rules", space_prompt)
        self.assertIn("只有世界生成时定义的规则", space_prompt)
        self.assertIn("只有世界生成时定义的规则", history_prompt)
        self.assertNotIn("个人要求：", space_prompt)
        self.assertNotIn("个人要求：", history_prompt)
        self.assertIn("多样化要求", space_prompt)
        self.assertIn("多样化要求", history_prompt)

    def test_agent_config_includes_generation_randomness(self) -> None:
        config = WorldGeneratorConfig()
        self.assertGreaterEqual(config.agent.temperature, 1.2)
        self.assertGreaterEqual(config.agent.top_p, 0.98)
        raw = config.to_dict()
        self.assertEqual(raw["agent"]["temperature"], config.agent.temperature)
        self.assertEqual(raw["agent"]["top_p"], config.agent.top_p)


if __name__ == "__main__":
    unittest.main()
