from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from .config import WorldGeneratorConfig
from .context import StoryContextBuilder
from .ids import path_distance, parse_path
from .storage import WorldStore


class InformationCollector:
    def __init__(
        self,
        config: WorldGeneratorConfig,
        runtime_root: Path | str = Path("runtime/worlds"),
    ) -> None:
        self.config = config
        self.runtime_root = Path(runtime_root)

    def collect(
        self,
        *,
        world_id: str,
        history_path: str,
        space_path: str,
        manager_notes: dict[str, Any] | None = None,
        story_phase: dict[str, Any] | None = None,
        interaction_count: int = 0,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        store = WorldStore(self.runtime_root, world_id)
        context = StoryContextBuilder(self.runtime_root).build(
            world_id=world_id,
            history_path=history_path,
            space_path=space_path,
        )
        characters = store.list_session_characters(session_id) if session_id else store.list_characters()
        protagonist = next((item for item in characters if item.get("role") == "protagonist"), None)
        others = [item for item in characters if item.get("role") != "protagonist"]
        rng = random.Random(
            f"{world_id}:{history_path}:{space_path}:{interaction_count}:{len(store.load_events(parse_path(history_path)))}"
        )

        current_events = store.load_events(parse_path(history_path))
        manager_notes = manager_notes or {}
        story_phase = story_phase or {"is_story_start": False, "phase": "continuation"}
        return {
            "instruction": "严格按照此信息创作。不要自行编造未知世界规则、未知历史、未知地点或未知人物事实。",
            "world_prompt": context["world"]["prompt"],
            "world_foundation": context["world"]["bootstrap"],
            "world_config": {
                "space_depth": context["world"]["config"].get("space_depth"),
                "history_depth": context["world"]["config"].get("history_depth"),
                "generation_requirements": self.config.story.generation_requirements,
            },
            "path_distance_rule": context["path_distance"]["rule"],
            "path_distance": context["path_distance"],
            "current_paths": {
                "history_path": parse_path(history_path),
                "space_path": parse_path(space_path),
            },
            "story_session": {
                "session_id": session_id,
            },
            "current": context["current"],
            "nearby": context["nearby"],
            "protagonist": protagonist,
            "other_characters": self._select_character_context(others, rng),
            "random_consistency_context": self._random_world_context(context, rng),
            "reusable_spacetime_characters": self._reusable_spacetime_characters(
                store,
                parse_path(history_path),
                parse_path(space_path),
            ),
            "reusable_story_context": self._reusable_story_context(
                store,
                parse_path(history_path),
                parse_path(space_path),
                session_id=session_id,
            ),
            "current_time_events": current_events,
            "current_time_event_groups": self._event_groups(current_events),
            "all_event_summary": self._event_summary(store),
            "key_facts": self._key_facts(
                context=context,
                protagonist=protagonist,
                others=others,
                current_events=current_events,
                manager_notes=manager_notes,
                story_phase=story_phase,
            ),
            "manager_notes": manager_notes,
            "story_phase": story_phase,
            "interaction_count": interaction_count,
            "generation_requirements": self.config.story.generation_requirements,
        }

    def _key_facts(
        self,
        *,
        context: dict[str, Any],
        protagonist: dict[str, Any] | None,
        others: list[dict[str, Any]],
        current_events: list[dict[str, Any]],
        manager_notes: dict[str, Any],
        story_phase: dict[str, Any],
    ) -> dict[str, Any]:
        world_rules = context["world"]["bootstrap"].get("world_rules") or []
        active_characters = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "summary": item.get("summary"),
            }
            for item in others
            if item.get("active", True)
        ]
        latest_events = [
            {
                "name": item.get("name"),
                "summary": item.get("summary"),
                "impact": item.get("impact"),
            }
            for item in current_events[-5:]
        ]
        known_world_new_story = bool(manager_notes.get("known_world_new_story"))
        return {
            "instruction": (
                "先读这里获取关键词，再用完整字段核对细节；不得把这里没有依据的信息扩展成事实。"
            ),
            "story_scope": (
                "已知世界的新故事：必须围绕既有世界规则、当前随机时空、已收集事件和人物信息展开。"
                if known_world_new_story
                else "当前故事：必须围绕既有世界规则、当前时空、事件和人物信息展开。"
            ),
            "world_rules": world_rules[:3],
            "current_history": self._compact_node(context["current"].get("history")),
            "current_space": self._compact_node(context["current"].get("space")),
            "protagonist": self._compact_character(protagonist),
            "active_characters": active_characters[:6],
            "latest_events": latest_events,
            "phase": story_phase,
            "manager_notice": {
                key: manager_notes.get(key)
                for key in (
                    "critical_story_notice",
                    "critical_character_notice",
                    "ending_outcome",
                    "known_world_new_story",
                    "time_or_space_changed",
                )
                if manager_notes.get(key) is not None
            },
        }

    def _compact_node(self, node: dict[str, Any] | None) -> dict[str, Any] | None:
        if not node:
            return None
        return {
            "path": node.get("path"),
            "name": node.get("name") or node.get("calendar"),
            "summary": node.get("summary"),
            "status": node.get("status"),
        }

    def _compact_character(self, character: dict[str, Any] | None) -> dict[str, Any] | None:
        if not character:
            return None
        return {
            "id": character.get("id"),
            "name": character.get("name"),
            "summary": character.get("summary"),
        }

    def _select_character_context(
        self,
        characters: list[dict[str, Any]],
        rng: random.Random,
    ) -> list[dict[str, Any]]:
        selected = []
        for character in characters:
            closeness = self._relationship_to_protagonist(character)
            base = (
                self.config.story.close_character_detail_base_probability
                if closeness >= 0.6
                else self.config.story.distant_character_detail_base_probability
            )
            include_detail = rng.random() < min(1.0, base + closeness * 0.15)
            selected.append(
                {
                    "id": character["id"],
                    "name": character["name"],
                    "summary": character["summary"],
                    "detail": character["detail"] if include_detail else None,
                    "relationships": character.get("relationships", []),
                    "active": character.get("active", True),
                }
            )
        return selected

    def _random_world_context(self, context: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        history = list(context["nearby"]["history"])
        space = list(context["nearby"]["space"])
        rng.shuffle(history)
        rng.shuffle(space)
        return {
            "history": history[: self.config.story.random_context_history_count],
            "space": space[: self.config.story.random_context_space_count],
        }

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
        *,
        session_id: str | None,
    ) -> list[dict[str, Any]]:
        reusable: list[dict[str, Any]] = []
        for session in store.list_sessions():
            if session_id and session.get("session_id") == session_id:
                continue
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

    def _event_summary(self, store: WorldStore) -> list[dict[str, Any]]:
        summary = []
        for event_file in store.list_event_files():
            events = event_file.get("events", [])
            if events:
                summary.append(
                    {
                        "history_path": event_file.get("history_path"),
                        "event_count": len(events),
                        "latest": events[-1],
                    }
                )
        return summary

    def _event_groups(self, events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        return {
            "public_events": [event for event in events if event.get("category") == "public"],
            "personal_events": [event for event in events if event.get("category") == "personal"],
            "story_events": [
                event
                for event in events
                if event.get("category") not in {"public", "personal"}
            ],
        }

    def _relationship_to_protagonist(self, character: dict[str, Any]) -> float:
        scores = [
            relation.get("closeness", 0)
            for relation in character.get("relationships", [])
            if relation.get("target_id") == "protagonist"
        ]
        return max(scores) if scores else 0.0

    def _compact_character(self, character: dict[str, Any] | None) -> dict[str, Any] | None:
        if not character:
            return None
        return {
            "id": character.get("id"),
            "name": character.get("name"),
            "role": character.get("role"),
            "summary": character.get("summary"),
            "active": character.get("active", True),
            "last_seen_session_id": character.get("last_seen_session_id") or character.get("story_session_id"),
        }
