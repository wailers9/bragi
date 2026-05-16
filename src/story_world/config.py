from __future__ import annotations

from dataclasses import dataclass, field
import dataclasses
from typing import Any


@dataclass(slots=True)
class AgentConfig:
    default_agent: str = "demo"
    model: str = "gpt-5.5"
    reasoning_effort: str | None = None
    temperature: float = 1.2
    top_p: float = 0.98


@dataclass(slots=True)
class RuntimeConfig:
    worlds_root: str = "runtime/worlds"


@dataclass(slots=True)
class WorldGenerationConfig:
    personal_requirements: str = "最多三条有趣、富有想象力的特殊底层规则，每条一句话；其它未列出的规则符合现实。"


@dataclass(slots=True)
class UpdateCadenceConfig:
    base_probability: float
    growth_per_turn: float
    max_probability: float


@dataclass(slots=True)
class StoryConfig:
    generation_requirements: str = "随机创作风格。"
    min_story_chars: int = 1000
    debug_story_agent_input: bool = False
    print_story_agent_input: bool = False
    continuity_recent_full_segments: int = 3
    continuity_older_summary_chars: int = 180
    random_context_history_count: int = 2
    random_context_space_count: int = 2
    close_character_detail_base_probability: float = 0.85
    distant_character_detail_base_probability: float = 0.25
    character_departure_probability: float = 0.2
    character_departure_relationship_weight: float = 0.8
    character_arrival_probability: float = 0.2
    character_extra_arrival_probability: float = 0.25
    character_max_new_arrivals: int = 3
    story_length_mode: str = "normal"
    ending_after_interactions: int = 3
    ending_probability: float = 0.5
    ending_modes: dict[str, dict[str, float | int | None]] = field(
        default_factory=lambda: {
            "normal": {"after_interactions": 3, "probability": 0.5},
            "long": {"after_interactions": 15, "probability": 0.1},
            "infinite": {"after_interactions": None, "probability": 0.0},
        }
    )
    update_cadence: str = "normal"
    update_cadences: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "slower": {"base_probability": 0.02, "growth_per_turn": 0.04, "max_probability": 0.45},
            "normal": {"base_probability": 0.05, "growth_per_turn": 0.08, "max_probability": 0.65},
            "faster": {"base_probability": 0.12, "growth_per_turn": 0.12, "max_probability": 0.85},
        }
    )

    def selected_update_cadence(self) -> UpdateCadenceConfig:
        raw = self.update_cadences.get(self.update_cadence) or self.update_cadences["normal"]
        return UpdateCadenceConfig(**raw)


@dataclass(slots=True)
class NeighborhoodConfig:
    space_radius_by_level: list[int] = field(default_factory=lambda: [0, 1, 1, 2])
    history_radius_by_level: list[int] = field(default_factory=lambda: [0, 0, 1, 1])


@dataclass(slots=True)
class WorldGeneratorConfig:
    agent: AgentConfig = field(default_factory=AgentConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    world_generation: WorldGenerationConfig = field(default_factory=WorldGenerationConfig)
    story: StoryConfig = field(default_factory=StoryConfig)
    space_depth: int = 3
    history_depth: int = 3
    space_default_branching: int = 3
    history_default_branching: int = 3
    neighborhood: NeighborhoodConfig = field(default_factory=NeighborhoodConfig)
    space_fields: dict[str, Any] = field(
        default_factory=lambda: {
            "cities": {"default_count": 3},
            "creatures": {"default_count": 4},
            "population": {"bands": ["稀疏", "中等", "密集"]},
        }
    )
    history_fields: dict[str, Any] = field(
        default_factory=lambda: {
            "public_events": {"default_count": 2},
            "personal_events": {"default_count": 3},
        }
    )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WorldGeneratorConfig":
        agent = AgentConfig(**raw.get("agent", {}))
        runtime = RuntimeConfig(**raw.get("runtime", {}))
        world_generation = WorldGenerationConfig(**raw.get("world_generation", {}))
        story_raw = dict(raw.get("story", {}))
        if "language_style" in story_raw and "generation_requirements" not in story_raw:
            story_raw["generation_requirements"] = story_raw.pop("language_style")
        else:
            story_raw.pop("language_style", None)
        if "update_cadences" not in story_raw and "base_time_update_probability" in story_raw:
            story_raw["update_cadences"] = {
                "normal": {
                    "base_probability": min(
                        story_raw.get("base_time_update_probability", 0.05),
                        story_raw.get("base_space_update_probability", 0.05),
                    ),
                    "growth_per_turn": story_raw.get("update_probability_growth", 0.08),
                    "max_probability": story_raw.get("max_update_probability", 0.65),
                }
            }
        for legacy_key in (
            "base_time_update_probability",
            "base_space_update_probability",
            "update_probability_growth",
            "max_update_probability",
        ):
            story_raw.pop(legacy_key, None)
        allowed_story_keys = {field.name for field in dataclasses.fields(StoryConfig)}
        story = StoryConfig(**{key: value for key, value in story_raw.items() if key in allowed_story_keys})
        neighborhood = NeighborhoodConfig(**raw.get("neighborhood", {}))
        return cls(
            agent=agent,
            runtime=runtime,
            world_generation=world_generation,
            story=story,
            space_depth=raw.get("space_depth", 3),
            history_depth=raw.get("history_depth", 3),
            space_default_branching=raw.get("space_default_branching", 3),
            history_default_branching=raw.get("history_default_branching", 3),
            neighborhood=neighborhood,
            space_fields=raw.get("space_fields", cls().space_fields),
            history_fields=raw.get("history_fields", cls().history_fields),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": {
                "default_agent": self.agent.default_agent,
                "model": self.agent.model,
                "reasoning_effort": self.agent.reasoning_effort,
                "temperature": self.agent.temperature,
                "top_p": self.agent.top_p,
            },
            "runtime": {
                "worlds_root": self.runtime.worlds_root,
            },
            "world_generation": {
                "personal_requirements": self.world_generation.personal_requirements,
            },
            "story": {
                "generation_requirements": self.story.generation_requirements,
                "min_story_chars": self.story.min_story_chars,
                "debug_story_agent_input": self.story.debug_story_agent_input,
                "print_story_agent_input": self.story.print_story_agent_input,
                "continuity_recent_full_segments": self.story.continuity_recent_full_segments,
                "continuity_older_summary_chars": self.story.continuity_older_summary_chars,
                "random_context_history_count": self.story.random_context_history_count,
                "random_context_space_count": self.story.random_context_space_count,
                "close_character_detail_base_probability": self.story.close_character_detail_base_probability,
                "distant_character_detail_base_probability": self.story.distant_character_detail_base_probability,
                "character_departure_probability": self.story.character_departure_probability,
                "character_departure_relationship_weight": self.story.character_departure_relationship_weight,
                "character_arrival_probability": self.story.character_arrival_probability,
                "character_extra_arrival_probability": self.story.character_extra_arrival_probability,
                "character_max_new_arrivals": self.story.character_max_new_arrivals,
                "story_length_mode": self.story.story_length_mode,
                "ending_after_interactions": self.story.ending_after_interactions,
                "ending_probability": self.story.ending_probability,
                "ending_modes": self.story.ending_modes,
                "update_cadence": self.story.update_cadence,
                "update_cadences": self.story.update_cadences,
            },
            "space_depth": self.space_depth,
            "history_depth": self.history_depth,
            "space_default_branching": self.space_default_branching,
            "history_default_branching": self.history_default_branching,
            "neighborhood": {
                "space_radius_by_level": self.neighborhood.space_radius_by_level,
                "history_radius_by_level": self.neighborhood.history_radius_by_level,
            },
            "space_fields": self.space_fields,
            "history_fields": self.history_fields,
        }
