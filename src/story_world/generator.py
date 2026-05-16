from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .agents import AgentResult, JsonAgent
from .config import WorldGeneratorConfig
from .ids import (
    NodePath,
    expand_neighbor_paths,
    first_level_paths,
    pad_path,
    parse_path,
    path_ancestors,
    path_distance_map,
    path_label,
    paths_from_manual_ranges,
)
from .prompts import (
    history_enrich_prompt,
    history_init_prompt,
    space_enrich_prompt,
    space_init_prompt,
    world_prompt,
)
from .schemas import (
    HISTORY_ENRICH_SCHEMA,
    HISTORY_SCHEMA,
    SPACE_ENRICH_SCHEMA,
    SPACE_SCHEMA,
    WORLD_SCHEMA,
)
from .storage import WorldStore


class WorldGenerator:
    def __init__(
        self,
        agent: JsonAgent,
        config: WorldGeneratorConfig | None = None,
        runtime_root: Path | str = Path("runtime/worlds"),
    ) -> None:
        self.agent = agent
        self.config = config or WorldGeneratorConfig()
        self.runtime_root = Path(runtime_root)

    def create_world(self, user_prompt: str, world_id: str | None = None) -> dict[str, Any]:
        world_id = world_id or uuid.uuid4().hex[:12]
        payload = self.agent.generate_json(
            world_prompt(user_prompt, self.config),
            schema_name="world_bootstrap",
            schema=WORLD_SCHEMA,
        )
        manifest = {
            "world_id": world_id,
            "prompt": user_prompt,
            "config": self.config.to_dict(),
            "bootstrap": dict(payload),
        }
        store = WorldStore(self.runtime_root, world_id)
        store.save_manifest(manifest)
        store.save_index({"history": {}, "space": {}})
        self._initialize_world_templates(store)
        self._record_usage(store, "world_bootstrap", payload)
        return manifest

    def initialize_context(
        self,
        *,
        world_id: str,
        user_prompt: str,
        history_path: str | NodePath,
        space_path: str | NodePath,
        protagonist_prompt: str | None = None,
        other_characters_prompt: str = "生成2到4个其它人物。",
        manual_history_ranges: dict[int, tuple[int, int]] | None = None,
        manual_space_ranges: dict[int, tuple[int, int]] | None = None,
    ) -> dict[str, Any]:
        current_history = self._normalize_history_path(parse_path(history_path))
        current_space = self._normalize_space_path(parse_path(space_path))

        history_paths = self._resolve_paths(
            current_history,
            manual_history_ranges,
            self.config.neighborhood.history_radius_by_level,
            self.config.history_default_branching,
        )
        space_paths = self._resolve_paths(
            current_space,
            manual_space_ranges,
            self.config.neighborhood.space_radius_by_level,
            self.config.space_default_branching,
        )

        store = WorldStore(self.runtime_root, world_id)
        world_foundation = store.load_manifest().get("bootstrap", {})
        self._materialize_history_path(store, current_history)
        history_payload = self.agent.generate_json(
            history_init_prompt(
                user_prompt,
                world_foundation,
                history_paths,
                current_history,
                self.config,
                self._history_relationship_context(current_history, history_paths),
            ),
            schema_name="history_context",
            schema=HISTORY_SCHEMA,
        )

        self._persist_nodes(
            store.save_history_node,
            store.load_history_node,
            history_payload.get("nodes", []),
            current_history,
        )
        self._persist_initial_events(store, current_history)
        self._materialize_space_path(store, current_history, current_space)
        space_payload = self.agent.generate_json(
            space_init_prompt(
                user_prompt,
                world_foundation,
                space_paths,
                current_space,
                self.config,
                self._space_relationship_context(current_history, current_space, history_paths, space_paths),
            ),
            schema_name="space_context",
            schema=SPACE_SCHEMA,
        )
        self._persist_nodes(
            lambda path, node: store.save_space_node_at_time(current_history, path, node),
            lambda path: store.load_space_node_at_time(current_history, path),
            space_payload.get("nodes", []),
            current_space,
        )
        self._record_usage(store, "history_context", history_payload)
        self._record_usage(store, "space_context", space_payload)
        character_payload = None
        if protagonist_prompt and not store.list_characters():
            from .characters import CharacterManager

            character_payload = CharacterManager(self.agent, self.runtime_root, self.config).initialize_characters(
                world_id=world_id,
                history_path=path_label(current_history),
                space_path=path_label(current_space),
                protagonist_prompt=protagonist_prompt,
                other_characters_prompt=other_characters_prompt,
            )

        return {
            "world_id": world_id,
            "current_history_path": list(current_history),
            "current_space_path": list(current_space),
            "history_paths_initialized": [list(path) for path in history_paths],
            "space_paths_initialized": [list(path) for path in space_paths],
            "history_payload": dict(history_payload),
            "space_payload": dict(space_payload),
            "character_payload": character_payload,
            "usage": {
                "history_context": history_payload.usage,
                "space_context": space_payload.usage,
                "character_initialization": character_payload["usage"] if character_payload else None,
            },
        }

    def enrich_history_node(
        self,
        *,
        world_id: str,
        user_prompt: str,
        history_path: str | NodePath,
    ) -> dict[str, Any]:
        path = self._normalize_history_path(parse_path(history_path))
        store = WorldStore(self.runtime_root, world_id)
        world_foundation = store.load_manifest().get("bootstrap", {})
        existing = store.load_history_node(path)
        payload = self.agent.generate_json(
            history_enrich_prompt(user_prompt, world_foundation, path, existing, self.config),
            schema_name="history_enrichment",
            schema=HISTORY_ENRICH_SCHEMA,
        )
        merged = self._merge_node(existing, payload["node"], retention="full")
        store.save_history_node(path, merged)
        self._record_usage(store, "history_enrichment", payload)
        return {"world_id": world_id, "history_path": list(path), "node": merged, "usage": payload.usage}

    def enrich_space_node(
        self,
        *,
        world_id: str,
        user_prompt: str,
        space_path: str | NodePath,
    ) -> dict[str, Any]:
        path = self._normalize_space_path(parse_path(space_path))
        store = WorldStore(self.runtime_root, world_id)
        world_foundation = store.load_manifest().get("bootstrap", {})
        existing = store.load_space_node(path)
        payload = self.agent.generate_json(
            space_enrich_prompt(user_prompt, world_foundation, path, existing, self.config),
            schema_name="space_enrichment",
            schema=SPACE_ENRICH_SCHEMA,
        )
        merged = self._merge_node(existing, payload["node"], retention="full")
        store.save_space_node(path, merged)
        self._record_usage(store, "space_enrichment", payload)
        return {"world_id": world_id, "space_path": list(path), "node": merged, "usage": payload.usage}

    def _resolve_paths(
        self,
        anchor: NodePath,
        manual_ranges: dict[int, tuple[int, int]] | None,
        radii: list[int],
        branching_factor: int,
    ) -> list[NodePath]:
        if manual_ranges:
            return paths_from_manual_ranges(manual_ranges, anchor, branching_factor)
        return expand_neighbor_paths(anchor, radii, branching_factor)

    def _initialize_world_templates(self, store: WorldStore) -> None:
        for path in first_level_paths(self.config.history_depth + 1, self.config.history_default_branching):
            if not self._node_exists(store.load_history_node, path):
                store.save_history_node(path, self._history_template_node(path, "first_level_time_template"))
        for path in first_level_paths(self.config.space_depth + 1, self.config.space_default_branching):
            if not self._node_exists(store.load_space_node, path):
                store.save_space_node(path, self._space_template_node(path, "first_level_space_template"))

    def _materialize_history_path(self, store: WorldStore, path: NodePath) -> None:
        for ancestor in path_ancestors(path):
            if not self._node_exists(store.load_history_node, ancestor):
                store.save_history_node(ancestor, self._history_template_node(ancestor, "pending_agent_completion"))

    def _materialize_space_path(self, store: WorldStore, history_path: NodePath, space_path: NodePath) -> None:
        for ancestor in path_ancestors(space_path):
            if not (store.space_node_dir(history_path, ancestor) / "node.json").exists():
                store.save_space_node_at_time(
                    history_path,
                    ancestor,
                    self._space_template_node(ancestor, "pending_agent_completion"),
                )

    def _history_template_node(self, path: NodePath, status: str) -> dict[str, Any]:
        return {
            "path": list(path),
            "calendar": "",
            "summary": "",
            "detail": None,
            "ongoing_events": None,
            "retention": status,
            "status": status,
        }

    def _space_template_node(self, path: NodePath, status: str) -> dict[str, Any]:
        return {
            "path": list(path),
            "name": "",
            "geography": "",
            "summary": "",
            "detail": None,
            "faction": None,
            "cities": None,
            "creatures": None,
            "population": None,
            "retention": status,
            "status": status,
        }

    def _history_relationship_context(self, current_history: NodePath, history_paths: list[NodePath]) -> dict[str, Any]:
        return {
            "current_history_path": list(current_history),
            "ancestor_paths": [list(path) for path in path_ancestors(current_history)],
            "requested_neighbor_paths": [list(path) for path in history_paths],
            "distance_from_current": path_distance_map(current_history, history_paths),
            "distance_rule": "编号越靠前的层级越大；共享前缀越长代表时间关系越近；同父级且末位差 1 表示相邻时间点。",
            "instruction": "先保持祖先时间节点的层级关系，再补全当前时间点与相邻时间概要。",
        }

    def _space_relationship_context(
        self,
        current_history: NodePath,
        current_space: NodePath,
        history_paths: list[NodePath],
        space_paths: list[NodePath],
    ) -> dict[str, Any]:
        return {
            "current_history_path": list(current_history),
            "current_space_path": list(current_space),
            "history_ancestor_paths": [list(path) for path in path_ancestors(current_history)],
            "space_ancestor_paths": [list(path) for path in path_ancestors(current_space)],
            "requested_history_neighbor_paths": [list(path) for path in history_paths],
            "requested_space_neighbor_paths": [list(path) for path in space_paths],
            "history_distance_from_current": path_distance_map(current_history, history_paths),
            "space_distance_from_current": path_distance_map(current_space, space_paths),
            "distance_rule": "编号越靠前的层级越大；共享前缀越长代表距离越近；同父级且末位差 1 表示相邻节点。",
            "instruction": "空间节点属于当前时间点；请说明该时间点下当前空间与相邻空间的关系。",
        }

    def _node_exists(self, loader: Any, path: NodePath) -> bool:
        try:
            loader(path)
        except FileNotFoundError:
            return False
        return True

    def _normalize_history_path(self, path: NodePath) -> NodePath:
        return pad_path(path, self.config.history_depth + 1)

    def _normalize_space_path(self, path: NodePath) -> NodePath:
        return pad_path(path, self.config.space_depth + 1)

    def _persist_nodes(
        self,
        writer: Any,
        reader: Any,
        nodes: list[dict[str, Any]],
        current_path: NodePath,
    ) -> None:
        seen_current = False
        for node in nodes:
            path = parse_path(node.get("path", []))
            if not path:
                continue
            if path == current_path:
                node["retention"] = "full"
                node["status"] = "full"
                seen_current = True
            else:
                node["retention"] = "initialized_summary"
                node["status"] = "summary"
            if self._should_keep_existing(reader, path, node):
                continue
            writer(path, node)
        if not seen_current:
            writer(
                current_path,
                {"path": list(current_path), "retention": "full", "status": "pending_agent_completion"},
            )

    def _persist_initial_events(self, store: WorldStore, current_history: NodePath) -> None:
        try:
            current = store.load_history_node(current_history)
        except FileNotFoundError:
            return
        events = self._events_from_history_node(current)
        if events:
            store.upsert_initial_events(current_history, events)

    def _events_from_history_node(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        ongoing = node.get("ongoing_events") or {}
        events: list[dict[str, Any]] = []
        for category, source_items in (
            ("public", ongoing.get("public_events") or []),
            ("personal", ongoing.get("personal_events") or []),
        ):
            for item in source_items:
                events.append(
                    {
                        "turn": 0,
                        "source": "history_initialization",
                        "category": category,
                        "name": item.get("name", ""),
                        "summary": item.get("summary", ""),
                        "impact": "初始化当前时间节点时生成，供故事 Agent 作为当前公共/人物事件背景。",
                    }
                )
        return events

    def _should_keep_existing(self, reader: Any, path: NodePath, incoming: dict[str, Any]) -> bool:
        try:
            existing = reader(path)
        except FileNotFoundError:
            return False
        if existing.get("status") == "full":
            return True
        return existing.get("status") == "summary" and incoming.get("status") == "summary"

    def _merge_node(
        self,
        existing: dict[str, Any],
        enriched: dict[str, Any],
        *,
        retention: str,
    ) -> dict[str, Any]:
        merged = {**existing, **enriched}
        merged["retention"] = retention
        merged["status"] = "full"
        return merged

    def _record_usage(self, store: WorldStore, call_type: str, result: AgentResult) -> None:
        usage = store.load_usage()
        usage["calls"].append({"type": call_type, **result.usage})
        totals = usage["totals"]
        totals["input_tokens"] += result.usage["input_tokens"]
        totals["output_tokens"] += result.usage["output_tokens"]
        totals["total_tokens"] += result.usage["total_tokens"]
        store.save_usage(usage)
