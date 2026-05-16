from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from .agents import AgentResult, JsonAgent
from .config import WorldGeneratorConfig
from .context import StoryContextBuilder
from .ids import path_distance, parse_path
from .prompts import character_addition_prompt, character_init_prompt
from .schemas import CHARACTER_ADDITION_SCHEMA, CHARACTER_INIT_SCHEMA
from .storage import WorldStore


class CharacterManager:
    def __init__(
        self,
        agent: JsonAgent,
        runtime_root: Path | str = Path("runtime/worlds"),
        config: WorldGeneratorConfig | None = None,
    ) -> None:
        self.agent = agent
        self.runtime_root = Path(runtime_root)
        self.config = config or WorldGeneratorConfig()

    def initialize_characters(
        self,
        *,
        world_id: str,
        history_path: str,
        space_path: str,
        protagonist_prompt: str,
        other_characters_prompt: str = "生成2到4个与主角和当前时间地点相关的其它人物。",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        context = StoryContextBuilder(self.runtime_root).build(
            world_id=world_id,
            history_path=history_path,
            space_path=space_path,
        )
        store = WorldStore(self.runtime_root, world_id)
        current_history = parse_path(history_path)
        current_space = parse_path(space_path)
        context["reusable_spacetime_characters"] = self._reusable_spacetime_characters(
            store,
            current_history,
            current_space,
        )
        context["reusable_story_context"] = self._reusable_story_context(
            store,
            current_history,
            current_space,
        )
        result = self.agent.generate_json(
            character_init_prompt(context, protagonist_prompt, other_characters_prompt),
            schema_name="character_initialization",
            schema=CHARACTER_INIT_SCHEMA,
        )
        for character in result["characters"]:
            if session_id:
                character["story_session_id"] = session_id
                store.save_session_character(session_id, character["id"], character)
            else:
                store.save_character(character["id"], character)
        self._snapshot_spacetime_characters(
            store,
            current_history,
            current_space,
            result["characters"],
            session_id=session_id,
            reason="story_start",
        )
        self._record_usage(store, "character_initialization", result)
        return {"world_id": world_id, "characters": result["characters"], "usage": result.usage}

    def list_characters(self, world_id: str) -> list[dict[str, Any]]:
        return WorldStore(self.runtime_root, world_id).list_characters()

    def update_active_characters(
        self,
        *,
        world_id: str,
        interaction_count: int,
    ) -> list[dict[str, Any]]:
        rng = random.Random(f"{world_id}:characters:{interaction_count}")
        result = self.update_character_roster(
            world_id=world_id,
            history_path=None,
            space_path=None,
            interaction_count=interaction_count,
            rng=rng,
        )
        return result["characters"]

    def update_character_roster(
        self,
        *,
        world_id: str,
        history_path: tuple[int, ...] | str | None,
        space_path: tuple[int, ...] | str | None,
        interaction_count: int,
        rng: random.Random,
        recent_story_state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        store = WorldStore(self.runtime_root, world_id)
        characters = store.list_session_characters(session_id) if session_id else store.list_characters()
        protagonist = next((item for item in characters if item.get("role") == "protagonist"), None)
        if protagonist is None:
            return self._roster_result(characters, [], [], [])
        departed: list[dict[str, Any]] = []
        retention_rolls: list[dict[str, Any]] = []
        for character in characters:
            if character.get("role") == "protagonist":
                character["active"] = True
            else:
                closeness = self._relationship_to_protagonist(character)
                leave_probability = self._departure_probability(closeness)
                roll = rng.random()
                retention_rolls.append(
                    {
                        "id": character["id"],
                        "closeness_to_protagonist": closeness,
                        "leave_probability": leave_probability,
                        "roll": roll,
                    }
                )
                if character.get("active", True) and roll < leave_probability:
                    character["active"] = False
                    departed.append(
                        {
                            "id": character["id"],
                            "name": character.get("name"),
                            "closeness_to_protagonist": closeness,
                            "leave_probability": leave_probability,
                        }
                    )
            self._save_character(store, character, session_id)
        if history_path is not None and space_path is not None:
            self._snapshot_spacetime_characters(
                store,
                parse_path(history_path),
                parse_path(space_path),
                characters,
                session_id=session_id,
                reason="roster_update_before_arrival",
            )

        joined = self._maybe_add_characters(
            store=store,
            world_id=world_id,
            history_path=history_path,
            space_path=space_path,
            interaction_count=interaction_count,
            rng=rng,
            departed_characters=departed,
            recent_story_state=recent_story_state or {},
            session_id=session_id,
        )
        characters = store.list_session_characters(session_id) if session_id else store.list_characters()
        if history_path is not None and space_path is not None:
            self._snapshot_spacetime_characters(
                store,
                parse_path(history_path),
                parse_path(space_path),
                characters,
                session_id=session_id,
                reason="roster_update_after_arrival",
            )
        return self._roster_result(characters, departed, joined, retention_rolls)

    def _maybe_add_characters(
        self,
        *,
        store: WorldStore,
        world_id: str,
        history_path: tuple[int, ...] | str | None,
        space_path: tuple[int, ...] | str | None,
        interaction_count: int,
        rng: random.Random,
        departed_characters: list[dict[str, Any]],
        recent_story_state: dict[str, Any],
        session_id: str | None,
    ) -> list[dict[str, Any]]:
        if rng.random() >= self.config.story.character_arrival_probability:
            return []
        count = 1
        while (
            count < self.config.story.character_max_new_arrivals
            and rng.random() < self.config.story.character_extra_arrival_probability
        ):
            count += 1
        characters = store.list_session_characters(session_id) if session_id else store.list_characters()
        context: dict[str, Any] = (
            StoryContextBuilder(self.runtime_root).build(
                world_id=world_id,
                history_path=history_path,
                space_path=space_path,
            )
            if history_path is not None and space_path is not None
            else {"world_id": world_id}
        )
        if history_path is not None:
            context["current_time_events"] = store.load_events(parse_path(history_path))
        context["recent_story_state"] = recent_story_state
        context["departed_characters_this_turn"] = departed_characters
        result = self.agent.generate_json(
            character_addition_prompt(
                context,
                characters,
                count,
                f"第 {interaction_count} 次互动后的人员流动，新人物应能解释为什么此刻进入当前时空。",
            ),
            schema_name="character_addition",
            schema=CHARACTER_ADDITION_SCHEMA,
        )
        existing_ids = {character["id"] for character in characters}
        joined = []
        for index, character in enumerate(result["characters"][:count], start=1):
            if character.get("role") == "protagonist":
                character["role"] = "other"
            character["active"] = True
            if character["id"] in existing_ids:
                character["id"] = f"other_new_{interaction_count}_{index}"
            existing_ids.add(character["id"])
            if session_id:
                character["story_session_id"] = session_id
            self._save_character(store, character, session_id)
            joined.append(
                {
                    "id": character["id"],
                    "name": character.get("name"),
                    "summary": character.get("summary"),
                }
            )
        self._record_usage(store, "character_addition", result)
        return joined

    def _snapshot_spacetime_characters(
        self,
        store: WorldStore,
        history_path: tuple[int, ...],
        space_path: tuple[int, ...],
        characters: list[dict[str, Any]],
        *,
        session_id: str | None,
        reason: str,
    ) -> None:
        for character in characters:
            payload = dict(character)
            payload["last_seen_history_path"] = list(history_path)
            payload["last_seen_space_path"] = list(space_path)
            payload["last_seen_session_id"] = session_id
            payload["spacetime_snapshot_reason"] = reason
            store.save_spacetime_character(history_path, space_path, payload["id"], payload)

    def _reusable_spacetime_characters(
        self,
        store: WorldStore,
        current_history: tuple[int, ...],
        current_space: tuple[int, ...],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for snapshot in store.list_all_spacetime_characters():
            history_path = parse_path(snapshot["history_path"])
            space_path = parse_path(snapshot["space_path"])
            h_distance = path_distance(current_history, history_path)
            s_distance = path_distance(current_space, space_path)
            for character in snapshot.get("characters", []):
                if character.get("role") == "protagonist":
                    continue
                candidates.append(
                    {
                        "history_path": list(history_path),
                        "space_path": list(space_path),
                        "history_shared_prefix_depth": h_distance["shared_prefix_depth"],
                        "space_shared_prefix_depth": s_distance["shared_prefix_depth"],
                        "history_absolute_steps": h_distance["absolute_steps"],
                        "space_absolute_steps": s_distance["absolute_steps"],
                        "character": self._compact_character(character),
                    }
                )
        candidates.sort(
            key=lambda item: (
                -int(item["history_shared_prefix_depth"]),
                -int(item["space_shared_prefix_depth"]),
                int(item["history_absolute_steps"]) + int(item["space_absolute_steps"]),
            )
        )
        return candidates[:8]

    def _reusable_story_context(
        self,
        store: WorldStore,
        current_history: tuple[int, ...],
        current_space: tuple[int, ...],
    ) -> list[dict[str, Any]]:
        reusable: list[dict[str, Any]] = []
        for session in store.list_sessions():
            history_path = parse_path(session.get("history_path", []))
            space_path = parse_path(session.get("space_path", []))
            if not history_path or not space_path:
                continue
            h_distance = path_distance(current_history, history_path)
            s_distance = path_distance(current_space, space_path)
            latest = (session.get("story_outputs") or [None])[-1] or {}
            ending = session.get("ending") or {}
            reusable.append(
                {
                    "session_id": session.get("session_id"),
                    "story_number": session.get("story_number"),
                    "ended": bool(session.get("ended")),
                    "history_path": list(history_path),
                    "space_path": list(space_path),
                    "history_shared_prefix_depth": h_distance["shared_prefix_depth"],
                    "space_shared_prefix_depth": s_distance["shared_prefix_depth"],
                    "latest_state": latest.get("state_notes") or latest.get("story", "")[:160],
                    "ending_state": ending.get("final_state"),
                }
            )
        reusable.sort(
            key=lambda item: (
                -int(item["history_shared_prefix_depth"]),
                -int(item["space_shared_prefix_depth"]),
                0 if item["ended"] else 1,
            )
        )
        return reusable[:5]

    def _compact_character(self, character: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": character.get("id"),
            "name": character.get("name"),
            "role": character.get("role"),
            "summary": character.get("summary"),
            "active": character.get("active", True),
            "last_seen_session_id": character.get("last_seen_session_id") or character.get("story_session_id"),
        }

    def _save_character(
        self,
        store: WorldStore,
        character: dict[str, Any],
        session_id: str | None,
    ) -> None:
        if session_id:
            store.save_session_character(session_id, character["id"], character)
        else:
            store.save_character(character["id"], character)

    def _departure_probability(self, closeness: float) -> float:
        base = self.config.story.character_departure_probability
        weight = self.config.story.character_departure_relationship_weight
        return max(0.0, min(1.0, base * (1.0 - weight * max(0.0, min(1.0, closeness)))))

    def _roster_result(
        self,
        characters: list[dict[str, Any]],
        departed: list[dict[str, Any]],
        joined: list[dict[str, Any]],
        retention_rolls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        changed = bool(departed or joined)
        notice = (
            "重要人物变化：本回合开始前，人物名单发生变化。写故事时必须解释旧人物为何暂时离开或新人物为何此刻加入，并让变化与当前时空、事件或主角选择有关。"
            if changed
            else "本回合人物名单未变化。"
        )
        return {
            "characters": characters,
            "active_characters": [item["id"] for item in characters if item.get("active")],
            "departed_characters": departed,
            "joined_characters": joined,
            "character_roster_changed": changed,
            "critical_character_notice": notice,
            "character_retention_rolls": retention_rolls,
        }

    def _relationship_to_protagonist(self, character: dict[str, Any]) -> float:
        scores = [
            relation.get("closeness", 0)
            for relation in character.get("relationships", [])
            if relation.get("target_id") == "protagonist"
        ]
        return max(scores) if scores else 0.0

    def _record_usage(self, store: WorldStore, call_type: str, result: AgentResult) -> None:
        usage = store.load_usage()
        usage["calls"].append({"type": call_type, **result.usage})
        totals = usage["totals"]
        totals["input_tokens"] += result.usage["input_tokens"]
        totals["output_tokens"] += result.usage["output_tokens"]
        totals["total_tokens"] += result.usage["total_tokens"]
        store.save_usage(usage)
