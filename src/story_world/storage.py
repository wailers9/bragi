from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ids import NodePath, path_ancestors, path_label


class WorldStore:
    def __init__(self, root: Path, world_id: str) -> None:
        self.base = root / world_id
        self.space_dir = self.base / "space"
        self.history_dir = self.base / "history"
        self.characters_dir = self.base / "characters"
        self.events_dir = self.base / "events"
        self.sessions_dir = self.base / "sessions"
        self.debug_dir = self.base / "debug"

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        self._write_json(self.base / "manifest.json", manifest)

    def save_index(self, index: dict[str, Any]) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        self._write_json(self.base / "index.json", index)

    def load_index(self) -> dict[str, Any]:
        path = self.base / "index.json"
        if not path.exists():
            return {"history": {}, "space": {}}
        return self._read_json(path)

    def load_manifest(self) -> dict[str, Any]:
        return self._read_json(self.base / "manifest.json")

    def save_usage(self, usage: dict[str, Any]) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        self._write_json(self.base / "usage.json", usage)

    def load_usage(self) -> dict[str, Any]:
        path = self.base / "usage.json"
        if not path.exists():
            return {"calls": [], "totals": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}
        return self._read_json(path)

    def save_space_node(self, path: NodePath, payload: dict[str, Any]) -> None:
        node_dir = self.global_space_node_dir(path)
        node_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(node_dir / "node.json", payload)
        self._update_index("space", path, payload)

    def load_space_node(self, path: NodePath) -> dict[str, Any]:
        nested_path = self.global_space_node_dir(path) / "node.json"
        if nested_path.exists():
            return self._read_json(nested_path)
        legacy_path = self.space_dir / f"{path_label(path)}.json"
        if legacy_path.exists():
            return self._read_json(legacy_path)
        index = self.load_index()
        matches = [
            entry
            for entry in index.get("space", {}).values()
            if tuple(entry.get("path", [])) == path
        ]
        if not matches:
            raise FileNotFoundError(f"Space node not found: {path_label(path)}")
        return self._read_json(self.base / matches[-1]["file"])

    def save_space_node_at_time(
        self,
        history_path: NodePath,
        space_path: NodePath,
        payload: dict[str, Any],
    ) -> None:
        node_dir = self.space_node_dir(history_path, space_path)
        node_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(node_dir / "node.json", payload)
        self._update_index("space", space_path, payload, history_path=history_path)

    def load_space_node_at_time(self, history_path: NodePath, space_path: NodePath) -> dict[str, Any]:
        path = self.space_node_dir(history_path, space_path) / "node.json"
        if path.exists():
            return self._read_json(path)
        return self.load_space_node(space_path)

    def save_history_node(self, path: NodePath, payload: dict[str, Any]) -> None:
        node_dir = self.history_node_dir(path)
        node_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(node_dir / "node.json", payload)
        self._update_index("history", path, payload)

    def load_history_node(self, path: NodePath) -> dict[str, Any]:
        nested_path = self.history_node_dir(path) / "node.json"
        if nested_path.exists():
            return self._read_json(nested_path)
        return self._read_json(self.history_dir / f"{path_label(path)}.json")

    def history_node_dir(self, path: NodePath) -> Path:
        node_dir = self.history_dir
        for ancestor in path_ancestors(path):
            node_dir = node_dir / path_label(ancestor)
        return node_dir

    def space_root_for_time(self, history_path: NodePath) -> Path:
        return self.history_node_dir(history_path) / "space"

    def global_space_node_dir(self, space_path: NodePath) -> Path:
        node_dir = self.space_dir
        for ancestor in path_ancestors(space_path):
            node_dir = node_dir / path_label(ancestor)
        return node_dir

    def space_node_dir(self, history_path: NodePath, space_path: NodePath) -> Path:
        node_dir = self.space_root_for_time(history_path)
        for ancestor in path_ancestors(space_path):
            node_dir = node_dir / path_label(ancestor)
        return node_dir

    def save_character(self, character_id: str, payload: dict[str, Any]) -> None:
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.characters_dir / f"{character_id}.json", payload)

    def save_session_character(self, session_id: str, character_id: str, payload: dict[str, Any]) -> None:
        directory = self.session_characters_dir(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        self._write_json(directory / f"{character_id}.json", payload)

    def load_character(self, character_id: str) -> dict[str, Any]:
        return self._read_json(self.characters_dir / f"{character_id}.json")

    def list_characters(self) -> list[dict[str, Any]]:
        if not self.characters_dir.exists():
            return []
        return [self._read_json(path) for path in sorted(self.characters_dir.glob("*.json"))]

    def session_characters_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id / "characters"

    def list_session_characters(self, session_id: str) -> list[dict[str, Any]]:
        directory = self.session_characters_dir(session_id)
        if not directory.exists():
            return []
        return [self._read_json(path) for path in sorted(directory.glob("*.json"))]

    def spacetime_characters_dir(self, history_path: NodePath, space_path: NodePath) -> Path:
        return self.space_node_dir(history_path, space_path) / "characters"

    def save_spacetime_character(
        self,
        history_path: NodePath,
        space_path: NodePath,
        character_id: str,
        payload: dict[str, Any],
    ) -> None:
        directory = self.spacetime_characters_dir(history_path, space_path)
        directory.mkdir(parents=True, exist_ok=True)
        self._write_json(directory / f"{character_id}.json", payload)

    def list_spacetime_characters(self, history_path: NodePath, space_path: NodePath) -> list[dict[str, Any]]:
        directory = self.spacetime_characters_dir(history_path, space_path)
        if not directory.exists():
            return []
        return [self._read_json(path) for path in sorted(directory.glob("*.json"))]

    def list_all_spacetime_characters(self) -> list[dict[str, Any]]:
        index = self.load_index()
        snapshots: list[dict[str, Any]] = []
        for entry in index.get("space", {}).values():
            history_path = tuple(entry.get("history_path") or [])
            space_path = tuple(entry.get("path") or [])
            if not history_path or not space_path:
                continue
            characters = self.list_spacetime_characters(history_path, space_path)
            if characters:
                snapshots.append(
                    {
                        "history_path": list(history_path),
                        "space_path": list(space_path),
                        "characters": characters,
                    }
                )
        return snapshots

    def save_session(self, session_id: str, payload: dict[str, Any]) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.sessions_dir / f"{session_id}.json", payload)

    def load_session(self, session_id: str) -> dict[str, Any]:
        return self._read_json(self.sessions_dir / f"{session_id}.json")

    def list_sessions(self) -> list[dict[str, Any]]:
        if not self.sessions_dir.exists():
            return []
        return [self._read_json(path) for path in sorted(self.sessions_dir.glob("*.json"))]

    def append_event(self, history_path: NodePath, event: dict[str, Any]) -> None:
        self.events_dir.mkdir(parents=True, exist_ok=True)
        path = self.events_dir / f"{path_label(history_path)}.json"
        events = self._read_json(path).get("events", []) if path.exists() else []
        events.append(event)
        self._write_json(path, {"history_path": list(history_path), "events": events})

    def append_place_event(self, history_path: NodePath, space_path: NodePath, event: dict[str, Any]) -> None:
        node = self.load_space_node_at_time(history_path, space_path)
        events = list(node.get("story_events") or [])
        events.append(event)
        node["story_events"] = events
        self.save_space_node_at_time(history_path, space_path, node)

    def upsert_initial_events(self, history_path: NodePath, events: list[dict[str, Any]]) -> None:
        self.events_dir.mkdir(parents=True, exist_ok=True)
        path = self.events_dir / f"{path_label(history_path)}.json"
        existing = self._read_json(path).get("events", []) if path.exists() else []
        existing_keys = {
            (event.get("source"), event.get("category"), event.get("name"))
            for event in existing
        }
        for event in events:
            key = (event.get("source"), event.get("category"), event.get("name"))
            if key not in existing_keys:
                existing.append(event)
                existing_keys.add(key)
        self._write_json(path, {"history_path": list(history_path), "events": existing})

    def load_events(self, history_path: NodePath) -> list[dict[str, Any]]:
        path = self.events_dir / f"{path_label(history_path)}.json"
        if not path.exists():
            return []
        return self._read_json(path).get("events", [])

    def list_event_files(self) -> list[dict[str, Any]]:
        if not self.events_dir.exists():
            return []
        return [self._read_json(path) for path in sorted(self.events_dir.glob("*.json"))]

    def save_debug_text(self, name: str, content: str) -> Path:
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        path = self.debug_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _update_index(
        self,
        section: str,
        path: NodePath,
        payload: dict[str, Any],
        *,
        history_path: NodePath | None = None,
    ) -> None:
        index = self.load_index()
        label = path_label(path)
        key = f"{path_label(history_path)}|{label}" if section == "space" and history_path else label
        file_path = (
            self.space_node_dir(history_path, path).relative_to(self.base) / "node.json"
            if section == "space" and history_path
            else self.history_node_dir(path).relative_to(self.base) / "node.json"
            if section == "history"
            else self.global_space_node_dir(path).relative_to(self.base) / "node.json"
            if section == "space"
            else Path(section) / f"{label}.json"
        )
        entry = {
            "path": list(path),
            "status": payload.get("status", payload.get("retention", "pending")),
            "retention": payload.get("retention"),
            "file": str(file_path),
        }
        if history_path is not None:
            entry["history_path"] = list(history_path)
        index[section][key] = entry
        self.save_index(index)
