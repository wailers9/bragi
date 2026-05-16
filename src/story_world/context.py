from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ids import NodePath, pad_path, parse_path, path_distance_map, path_label
from .storage import WorldStore


@dataclass(slots=True)
class StoryContextBuilder:
    runtime_root: Path | str = Path("runtime/worlds")

    def build(
        self,
        *,
        world_id: str,
        history_path: str | NodePath,
        space_path: str | NodePath,
    ) -> dict[str, Any]:
        store = WorldStore(Path(self.runtime_root), world_id)
        manifest = store.load_manifest()
        index = store.load_index()
        config = manifest["config"]
        history = pad_path(parse_path(history_path), config.get("history_depth", 3) + 1)
        space = pad_path(parse_path(space_path), config.get("space_depth", 3) + 1)
        history_label = path_label(history)
        space_label = path_label(space)
        space_key = f"{history_label}|{space_label}"
        space_entries = {
            label: entry
            for label, entry in index["space"].items()
            if entry.get("history_path") == list(history)
        }

        return {
            "world_id": world_id,
            "world": {
                "prompt": manifest["prompt"],
                "bootstrap": manifest["bootstrap"],
                "config": manifest["config"],
            },
            "current": {
                "history": store.load_history_node(history),
                "space": store.load_space_node_at_time(history, space),
            },
            "nearby": {
                "history": self._load_related(store, index["history"], history, current_label=history_label, loader=store.load_history_node),
                "space": self._load_related(
                    store,
                    space_entries,
                    space,
                    current_label=space_key,
                    loader=lambda path: store.load_space_node_at_time(history, path),
                ),
            },
            "path_distance": {
                "rule": "编号越靠前的层级越大；共享前缀越长代表距离越近；同父级且末位差 1 表示相邻节点。",
                "history": path_distance_map(
                    history,
                    [
                        parse_path(entry["path"])
                        for label, entry in sorted(index["history"].items())
                        if label != history_label
                    ],
                ),
                "space": path_distance_map(
                    space,
                    [
                        parse_path(entry["path"])
                        for label, entry in sorted(space_entries.items())
                        if label != space_key
                    ],
                ),
            },
            "index_summary": {
                "history_count": len(index["history"]),
                "space_count": len(index["space"]),
                "full_history_count": self._count_status(index["history"], "full"),
                "full_space_count": self._count_status(index["space"], "full"),
            },
        }

    def _load_related(
        self,
        store: WorldStore,
        entries: dict[str, dict[str, Any]],
        anchor: NodePath,
        *,
        current_label: str,
        loader: Any,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        anchor_parent = anchor[:-1]
        for label, entry in sorted(entries.items()):
            if label == current_label:
                continue
            path = parse_path(entry["path"])
            if path[:-1] == anchor_parent or path[:-2] == anchor[:-2]:
                results.append(loader(path))
        return results

    def _count_status(self, entries: dict[str, dict[str, Any]], status: str) -> int:
        return sum(1 for entry in entries.values() if entry.get("status") == status)
