from __future__ import annotations

import random
import uuid
from pathlib import Path
from typing import Any

from .agents import JsonAgent
from .characters import CharacterManager
from .collector import InformationCollector
from .config import WorldGeneratorConfig
from .generator import WorldGenerator
from .ids import NodePath, parse_path, path_label
from .prompts import intro_prompt, story_create_prompt, story_ending_prompt
from .schemas import ENDING_SCHEMA, INTRO_SCHEMA, STORY_SCHEMA
from .storage import WorldStore


class StorySessionManager:
    def __init__(
        self,
        *,
        agent: JsonAgent,
        config: WorldGeneratorConfig,
        runtime_root: Path | str = Path("runtime/worlds"),
    ) -> None:
        self.agent = agent
        self.config = config
        self.runtime_root = Path(runtime_root)
        self.generator = WorldGenerator(agent=agent, config=config, runtime_root=runtime_root)
        self.characters = CharacterManager(agent=agent, runtime_root=runtime_root, config=config)
        self.collector = InformationCollector(config=config, runtime_root=runtime_root)

    def start(
        self,
        *,
        world_id: str,
        history_path: str,
        space_path: str,
        protagonist_prompt: str,
        other_characters_prompt: str = "生成2到4个其它人物。",
        generation_requirements: str | None = None,
        session_id: str | None = None,
        story_number: int | None = None,
        story_length_mode: str | None = None,
        agent_selection: dict[str, str] | None = None,
        generate_first_segment: bool = True,
    ) -> dict[str, Any]:
        session_id = session_id or uuid.uuid4().hex[:12]
        store = WorldStore(self.runtime_root, world_id)
        story_number = story_number or self._next_story_number(store)
        manifest = store.load_manifest()
        self.generator.initialize_context(
            world_id=world_id,
            user_prompt=manifest["prompt"],
            history_path=history_path,
            space_path=space_path,
        )
        self.characters.initialize_characters(
            world_id=world_id,
            history_path=history_path,
            space_path=space_path,
            protagonist_prompt=protagonist_prompt,
            other_characters_prompt=other_characters_prompt,
            session_id=session_id,
        )
        session = {
            "session_id": session_id,
            "story_number": story_number,
            "known_world_new_story": story_number > 1,
            "agent_selection": agent_selection or {},
            "story_length_mode": self._normalize_story_length_mode(story_length_mode),
            "ending_policy": self._ending_policy(story_length_mode),
            "world_id": world_id,
            "history_path": list(parse_path(history_path)),
            "space_path": list(parse_path(space_path)),
            "interaction_count": 0,
            "turns_since_time_update": 0,
            "turns_since_space_update": 0,
            "generation_requirements": generation_requirements or self.config.story.generation_requirements,
            "ended": False,
            "choices": [],
            "story_outputs": [],
            "ending": None,
        }
        store.save_session(session_id, session)
        intro_payload = self.generate_intro(session_id=session_id)
        if not generate_first_segment:
            return self._intro_result(store, store.load_session(session_id))
        return self.generate_next(
            session_id=session_id,
            manager_notes={"reason": "story_start"},
            is_story_start=True,
            intro_payload=intro_payload,
        )

    def begin_story(self, *, session_id: str) -> dict[str, Any]:
        store = self._store_for_session(session_id)
        session = store.load_session(session_id)
        if session.get("ended"):
            return self._ended_result(store, session)
        if session.get("story_outputs"):
            history_label = path_label(tuple(session["history_path"]))
            space_label = path_label(tuple(session["space_path"]))
            collected = self.collector.collect(
                world_id=session["world_id"],
                history_path=history_label,
                space_path=space_label,
                manager_notes={"story_already_started": True},
                story_phase=self._story_phase(session, False),
                interaction_count=session["interaction_count"],
                session_id=session_id,
            )
            return {
                "session": session,
                "collected_context": collected,
                "output": session["story_outputs"][-1],
                "intro": session.get("intro"),
            }
        return self.generate_next(
            session_id=session_id,
            manager_notes={"reason": "user_confirmed_after_intro"},
            is_story_start=True,
            intro_payload=session.get("intro"),
        )

    def load(self, *, session_id: str) -> dict[str, Any]:
        store = self._store_for_session(session_id)
        session = store.load_session(session_id)
        if session.get("ended"):
            return self._ended_result(store, session)
        history_label = path_label(tuple(session["history_path"]))
        space_label = path_label(tuple(session["space_path"]))
        phase = "continuation" if session.get("story_outputs") else "intro_waiting"
        collected = self.collector.collect(
            world_id=session["world_id"],
            history_path=history_label,
            space_path=space_label,
            manager_notes={"loaded_from_storage": True},
            story_phase={"is_story_start": not bool(session.get("story_outputs")), "phase": phase},
            interaction_count=session["interaction_count"],
            session_id=session_id,
        )
        return {
            "session": session,
            "collected_context": collected,
            "output": session["story_outputs"][-1] if session.get("story_outputs") else None,
            "intro": session.get("intro"),
            "ending": session.get("ending"),
        }

    def generate_intro(self, *, session_id: str) -> dict[str, Any]:
        store = self._store_for_session(session_id)
        session = store.load_session(session_id)
        history_label = path_label(tuple(session["history_path"]))
        space_label = path_label(tuple(session["space_path"]))
        context = self.collector.collect(
            world_id=session["world_id"],
            history_path=history_label,
            space_path=space_label,
            manager_notes={
                "reason": "intro_before_story_start",
                "intro_variation": self._intro_variation(),
                **self._known_world_story_notes(session),
            },
            story_phase={"is_story_start": True, "phase": "intro"},
            interaction_count=session["interaction_count"],
            session_id=session_id,
        )
        result = self.agent.generate_json(
            intro_prompt(
                context,
                session.get("generation_requirements", self.config.story.generation_requirements),
            ),
            schema_name="story_intro",
            schema=INTRO_SCHEMA,
        )
        payload = dict(result)
        payload["usage"] = result.usage
        session["intro"] = payload
        store.save_session(session_id, session)
        self.generator._record_usage(store, "story_intro", result)
        return payload

    def _intro_variation(self) -> dict[str, str]:
        rng = random.SystemRandom()
        return {
            "opening_mode": rng.choice(
                [
                    "从一个具体动作开场",
                    "从一句正在发生的对话开场",
                    "从一份公告、账单、判决或求救信开场",
                    "从一个异常物件被发现开场",
                    "从主角正在处理的日常麻烦开场",
                    "从公共危机突然打断私人事务开场",
                ]
            ),
            "focus_mode": rng.choice(
                [
                    "先写人物压力，再带出世界规则",
                    "先写当前地点的社会秩序，再带出主角困境",
                    "先写一个小事件如何牵动大矛盾",
                    "先写主角与一个具体人物的关系张力",
                ]
            ),
            "avoid_structure": "不要用固定的历法年份开头，不要按世界概述、地点介绍、主角履历、多方势力名单的顺序展开。",
        }

    def submit_choice(self, *, session_id: str, choice_id: str = "CONTINUE", choice_text: str | None = None) -> dict[str, Any]:
        store = self._store_for_session(session_id)
        session = store.load_session(session_id)
        if session.get("ended"):
            return self._ended_result(store, session)
        normalized_text = (choice_text or "").strip()
        session["choices"].append(
            {
                "id": choice_id or "CONTINUE",
                "text": normalized_text or "用户未输入导向，直接推进故事。",
                "turn": session["interaction_count"],
            }
        )
        session["interaction_count"] += 1
        session["turns_since_time_update"] = session.get("turns_since_time_update", 0) + 1
        session["turns_since_space_update"] = session.get("turns_since_space_update", 0) + 1
        updates = self._update_world_state(store, session)
        store.save_session(session_id, session)
        if self._should_end_story(session):
            return self.generate_ending(session_id=session_id, manager_notes=updates)
        return self.generate_next(session_id=session_id, manager_notes=updates, is_story_start=False)

    def generate_ending(self, *, session_id: str, manager_notes: dict[str, Any]) -> dict[str, Any]:
        store = self._store_for_session(session_id)
        session = store.load_session(session_id)
        history_label = path_label(tuple(session["history_path"]))
        space_label = path_label(tuple(session["space_path"]))
        policy = session.get("ending_policy") or self._ending_policy(session.get("story_length_mode"))
        ending_notes = {
            **manager_notes,
            **self._ending_outcome(session),
            "forced_story_ending": True,
            "critical_story_notice": (
                f"故事结束管理器触发：{policy.get('mode', 'normal')} 模式下互动次数已大于 {policy.get('after_interactions')}，"
                "本回合必须结束当前故事，给出清楚结尾。"
            ),
        }
        collected = self.collector.collect(
            world_id=session["world_id"],
            history_path=history_label,
            space_path=space_label,
            manager_notes=ending_notes,
            story_phase={"is_story_start": False, "phase": "ending", "instruction": "这是当前故事结尾。"},
            interaction_count=session["interaction_count"],
            session_id=session_id,
        )
        self._attach_story_history_if_needed(session, collected)
        result = self.agent.generate_json(
            story_ending_prompt(
                collected,
                session["choices"],
                session["story_outputs"][-1] if session.get("story_outputs") else None,
                session.get("generation_requirements", self.config.story.generation_requirements),
            ),
            schema_name="story_ending",
            schema=ENDING_SCHEMA,
        )
        ending = dict(result)
        ending["usage"] = result.usage
        session["ended"] = True
        session["ending"] = ending
        ending_event = {
            "turn": session["interaction_count"],
            "source": "story_ending",
            "category": "story",
            "name": f"故事 {session.get('story_number', '?')} 结束",
            "summary": ending["final_state"],
            "impact": "当前故事已结束；事件保留在世界时间和地点文件中，供同一世界下其它故事引用。",
            "session_id": session_id,
            "story_number": session.get("story_number"),
        }
        store.append_event(tuple(session["history_path"]), ending_event)
        store.append_place_event(tuple(session["history_path"]), tuple(session["space_path"]), ending_event)
        store.save_session(session_id, session)
        self.generator._record_usage(store, "story_ending", result)
        return {"session": session, "collected_context": collected, "output": None, "intro": session.get("intro"), "ending": ending}

    def generate_next(
        self,
        *,
        session_id: str,
        manager_notes: dict[str, Any],
        is_story_start: bool | None = None,
        intro_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        store = self._store_for_session(session_id)
        session = store.load_session(session_id)
        history_label = path_label(tuple(session["history_path"]))
        space_label = path_label(tuple(session["space_path"]))
        effective_manager_notes = {
            **manager_notes,
            **(self._known_world_story_notes(session) if self._story_phase(session, is_story_start)["is_story_start"] else {}),
        }
        collected = self.collector.collect(
            world_id=session["world_id"],
            history_path=history_label,
            space_path=space_label,
            manager_notes=effective_manager_notes,
            story_phase=self._story_phase(session, is_story_start),
            interaction_count=session["interaction_count"],
            session_id=session_id,
        )
        self._attach_story_history_if_needed(session, collected)
        result = self.agent.generate_json(
            self._story_agent_prompt(store, session, collected),
            schema_name="story_segment",
            schema=STORY_SCHEMA,
        )
        output = dict(result)
        output["usage"] = result.usage
        session["story_outputs"].append(output)
        for event in output["new_events"]:
            stored_event = {
                "turn": session["interaction_count"],
                "source": "story_segment",
                "category": "story",
                "session_id": session_id,
                "story_number": session.get("story_number"),
                **event,
            }
            store.append_event(tuple(session["history_path"]), stored_event)
            store.append_place_event(tuple(session["history_path"]), tuple(session["space_path"]), stored_event)
        store.save_session(session_id, session)
        self.generator._record_usage(store, "story_segment", result)
        if intro_payload is None:
            intro_payload = session.get("intro")
        return {"session": session, "collected_context": collected, "output": output, "intro": intro_payload}

    def _attach_story_history_if_needed(self, session: dict[str, Any], collected: dict[str, Any]) -> None:
        segments = session.get("story_outputs") or []
        if not segments and not session.get("intro") and not session.get("choices"):
            return
        recent_count = max(1, self.config.story.continuity_recent_full_segments)
        split_at = max(0, len(segments) - recent_count)
        collected["story_history"] = {
            "continuity_instruction": (
                "必须把 recent_full_segments 当作已经发生的最近完整前文来承接。"
                "older_segments_compact 只保留更早情节的摘要、用户导向、事件和状态备注，用于长期一致性。"
                "每次续写都要先承接最近一段结尾、用户导向、人物状态和事件后果。"
                "如果 manager_notes.time_or_space_changed 为 true，再自然解释时间或地点如何变化；"
                "不得突然换场、重启故事或忽略前文。"
            ),
            "intro": session.get("intro"),
            "user_inputs": session.get("choices", []),
            "older_segments_compact": [
                {
                    "turn": index,
                    "story_excerpt": self._truncate_text(
                        segment.get("story", ""),
                        self.config.story.continuity_older_summary_chars,
                    ),
                    "new_events": segment.get("new_events", []),
                    "state_notes": segment.get("state_notes", ""),
                    "user_input_after_segment": self._choice_for_turn(session, index),
                }
                for index, segment in enumerate(segments[:split_at])
            ],
            "recent_full_segments": [
                {
                    "turn": split_at + index,
                    "story": segment.get("story", ""),
                    "new_events": segment.get("new_events", []),
                    "state_notes": segment.get("state_notes", ""),
                    "user_input_after_segment": self._choice_for_turn(session, split_at + index),
                }
                for index, segment in enumerate(segments[split_at:])
            ],
            "latest_segment": (segments or [None])[-1],
            "ending": session.get("ending"),
        }

    def _choice_for_turn(self, session: dict[str, Any], turn: int) -> dict[str, Any] | None:
        for choice in session.get("choices", []):
            if choice.get("turn") == turn:
                return choice
        return None

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."

    def _story_agent_prompt(
        self,
        store: WorldStore,
        session: dict[str, Any],
        collected: dict[str, Any],
    ) -> str:
        prompt = story_create_prompt(
            collected,
            session["choices"],
            session.get(
                "generation_requirements",
                session.get("language_style", self.config.story.generation_requirements),
            ),
            self.config.story.min_story_chars,
        )
        if self.config.story.debug_story_agent_input:
            name = (
                f"story_{session.get('story_number', 'unknown')}_"
                f"{session['session_id']}_turn_{session['interaction_count']:04d}.txt"
            )
            store.save_debug_text(name, prompt)
            store.save_debug_text(f"story_agent_input_turn_{session['interaction_count']:04d}.txt", prompt)
        if self.config.story.print_story_agent_input:
            print(prompt)
        return prompt

    def _story_phase(self, session: dict[str, Any], is_story_start: bool | None) -> dict[str, Any]:
        if is_story_start is None:
            is_story_start = not session.get("story_outputs")
        instruction = (
            "这是整个故事的开头。请建立开篇场景、主角处境、当前矛盾和行动动机。"
            if is_story_start
            else "这是续写。请承接主角选择、既有事件和当前时间地点。"
        )
        if is_story_start and session.get("known_world_new_story"):
            instruction += "这是同一已知世界里的新故事；必须围绕世界底层规则、当前随机时空、既有事件摘要和收集到的人物/地点/历史信息展开。"
        return {
            "is_story_start": is_story_start,
            "phase": "opening" if is_story_start else "continuation",
            "instruction": instruction,
        }

    def _known_world_story_notes(self, session: dict[str, Any]) -> dict[str, Any]:
        if not session.get("known_world_new_story"):
            return {}
        return {
            "known_world_new_story": True,
            "critical_story_notice": (
                "这是同一已知世界里的新故事：必须围绕已有世界底层规则、当前随机时空、"
                "已收集事件和人物信息展开；可以换主角和切入点，但不能脱离这个世界。"
            ),
        }

    def _ending_outcome(self, session: dict[str, Any]) -> dict[str, str]:
        rng = random.Random(f"{session['session_id']}:ending-outcome")
        outcome = "good" if rng.random() < 0.5 else "bad"
        label = "好结局" if outcome == "good" else "坏结局"
        return {
            "ending_outcome": outcome,
            "ending_outcome_notice": f"本次结尾目标为{label}；必须合理承接前文，不要强行反转。",
        }

    def _update_world_state(self, store: WorldStore, session: dict[str, Any]) -> dict[str, Any]:
        rng = random.Random(f"{session['session_id']}:{session['interaction_count']}")
        old_history = tuple(session["history_path"])
        old_space = tuple(session["space_path"])
        time_probability = self._update_probability(session.get("turns_since_time_update", 0))
        space_probability = self._update_probability(session.get("turns_since_space_update", 0))
        new_history = self._maybe_advance_time(old_history, time_probability, rng)
        new_space = self._maybe_move_space(old_space, space_probability, rng)
        changed = new_history != old_history or new_space != old_space
        if new_history != old_history:
            session["turns_since_time_update"] = 0
        if new_space != old_space:
            session["turns_since_space_update"] = 0
        session["history_path"] = list(new_history)
        session["space_path"] = list(new_space)
        if changed:
            manifest = store.load_manifest()
            self.generator.initialize_context(
                world_id=session["world_id"],
                user_prompt=manifest["prompt"],
                history_path=new_history,
                space_path=new_space,
            )
        character_updates = self.characters.update_character_roster(
            world_id=session["world_id"],
            history_path=new_history,
            space_path=new_space,
            interaction_count=session["interaction_count"],
            rng=rng,
            recent_story_state={
                "latest_choice": session["choices"][-1] if session["choices"] else None,
                "previous_history_path": list(old_history),
                "previous_space_path": list(old_space),
                "current_history_path": list(new_history),
                "current_space_path": list(new_space),
                "time_or_space_changed": changed,
                "interaction_count": session["interaction_count"],
            },
            session_id=session["session_id"],
        )
        critical_notice = (
            "重要状态变化：本回合开始前，故事的当前时间或当前空间已经更新。"
            "写故事时必须承认这个变化，使用 current_history_path/current_space_path 的新设定，"
            "并自然交代角色如何进入或感知新时空。"
            if changed
            else "本回合时间和空间未变化，继续沿用当前时空。"
        )
        return {
            "previous_history_path": list(old_history),
            "previous_space_path": list(old_space),
            "current_history_path": list(new_history),
            "current_space_path": list(new_space),
            "time_or_space_changed": changed,
            "critical_story_notice": critical_notice,
            "time_update_probability": time_probability,
            "space_update_probability": space_probability,
            "turns_since_time_update": session.get("turns_since_time_update", 0),
            "turns_since_space_update": session.get("turns_since_space_update", 0),
            "active_characters": character_updates["active_characters"],
            "departed_characters": character_updates["departed_characters"],
            "joined_characters": character_updates["joined_characters"],
            "character_roster_changed": character_updates["character_roster_changed"],
            "critical_character_notice": character_updates["critical_character_notice"],
            "character_retention_rolls": character_updates["character_retention_rolls"],
            "latest_choice": session["choices"][-1] if session["choices"] else None,
        }

    def _update_probability(self, turns_since_update: int) -> float:
        cadence = self.config.story.selected_update_cadence()
        return min(
            cadence.max_probability,
            cadence.base_probability + turns_since_update * cadence.growth_per_turn,
        )

    def _maybe_advance_time(self, path: NodePath, probability: float, rng: random.Random) -> NodePath:
        if rng.random() >= probability:
            return path
        return path[:-1] + (path[-1] + 1,)

    def _maybe_move_space(self, path: NodePath, probability: float, rng: random.Random) -> NodePath:
        if rng.random() >= probability:
            return path
        step = 1 if rng.random() >= 0.5 else -1
        return path[:-1] + (max(1, path[-1] + step),)

    def _should_end_story(self, session: dict[str, Any]) -> bool:
        if session.get("ended"):
            return False
        policy = session.get("ending_policy") or self._ending_policy(session.get("story_length_mode"))
        if policy.get("mode") == "infinite":
            return False
        after_interactions = policy.get("after_interactions")
        if after_interactions is None:
            return False
        if session["interaction_count"] <= int(after_interactions):
            return False
        rng = random.Random(f"{session['session_id']}:ending:{session['interaction_count']}")
        return rng.random() < float(policy.get("probability", 0.0))

    def _normalize_story_length_mode(self, mode: str | None) -> str:
        selected = (mode or self.config.story.story_length_mode or "long").strip().lower()
        return selected if selected in self.config.story.ending_modes else "long"

    def _ending_policy(self, mode: str | None) -> dict[str, Any]:
        selected = self._normalize_story_length_mode(mode)
        raw = self.config.story.ending_modes.get(selected) or {}
        if selected == "normal" and not raw:
            raw = {
                "after_interactions": self.config.story.ending_after_interactions,
                "probability": self.config.story.ending_probability,
            }
        return {
            "mode": selected,
            "after_interactions": raw.get("after_interactions"),
            "probability": raw.get("probability", 0.0),
        }

    def session_token_usage(self, session: dict[str, Any]) -> dict[str, int]:
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        candidates = []
        if session.get("intro"):
            candidates.append(session["intro"])
        candidates.extend(session.get("story_outputs") or [])
        if session.get("ending"):
            candidates.append(session["ending"])
        for payload in candidates:
            usage = payload.get("usage") or {}
            for key in totals:
                totals[key] += int(usage.get(key, 0) or 0)
        return totals

    def _intro_result(self, store: WorldStore, session: dict[str, Any]) -> dict[str, Any]:
        history_label = path_label(tuple(session["history_path"]))
        space_label = path_label(tuple(session["space_path"]))
        collected = self.collector.collect(
            world_id=session["world_id"],
            history_path=history_label,
            space_path=space_label,
            manager_notes={"awaiting_user_after_intro": True},
            story_phase={"is_story_start": True, "phase": "intro_waiting"},
            interaction_count=session["interaction_count"],
            session_id=session["session_id"],
        )
        return {
            "session": session,
            "collected_context": collected,
            "output": None,
            "intro": session.get("intro"),
        }

    def _next_story_number(self, store: WorldStore) -> int:
        numbers = [
            int(session.get("story_number", 0))
            for session in store.list_sessions()
            if isinstance(session.get("story_number", 0), int)
        ]
        return (max(numbers) if numbers else 0) + 1

    def _ended_result(self, store: WorldStore, session: dict[str, Any]) -> dict[str, Any]:
        history_label = path_label(tuple(session["history_path"]))
        space_label = path_label(tuple(session["space_path"]))
        collected = self.collector.collect(
            world_id=session["world_id"],
            history_path=history_label,
            space_path=space_label,
            manager_notes={"story_already_ended": True},
            story_phase={"is_story_start": False, "phase": "ended"},
            interaction_count=session["interaction_count"],
            session_id=session["session_id"],
        )
        return {
            "session": session,
            "collected_context": collected,
            "output": session["story_outputs"][-1] if session.get("story_outputs") else None,
            "intro": session.get("intro"),
            "ending": session.get("ending"),
        }

    def _store_for_session(self, session_id: str) -> WorldStore:
        worlds_root = Path(self.runtime_root)
        for world_dir in worlds_root.iterdir() if worlds_root.exists() else []:
            candidate = WorldStore(worlds_root, world_dir.name)
            session_path = candidate.sessions_dir / f"{session_id}.json"
            if session_path.exists():
                return candidate
        raise FileNotFoundError(f"Story session not found: {session_id}")
