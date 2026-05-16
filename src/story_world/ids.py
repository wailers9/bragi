from __future__ import annotations

from collections.abc import Iterable
import re


NodePath = tuple[int, ...]


def parse_path(raw: str | Iterable[int]) -> NodePath:
    if isinstance(raw, str):
        values = [part.strip() for part in re.split(r"[,.]", raw) if part.strip()]
        return tuple(int(part) for part in values)
    return tuple(int(part) for part in raw)


def path_label(path: NodePath) -> str:
    return ".".join(str(part) for part in path)


def pad_path(path: NodePath, depth: int) -> NodePath:
    if len(path) >= depth:
        return path
    return path + (0,) * (depth - len(path))


def path_ancestors(path: NodePath) -> list[NodePath]:
    ancestors: list[NodePath] = []
    for index, value in enumerate(path):
        if value == 0 and any(path[index + 1 :]):
            continue
        ancestor = path[: index + 1] + (0,) * (len(path) - index - 1)
        if ancestor not in ancestors:
            ancestors.append(ancestor)
    return ancestors


def first_level_paths(depth: int, branching_factor: int) -> list[NodePath]:
    return [tuple([index] + [0] * (depth - 1)) for index in range(max(0, branching_factor))]


def path_distance(anchor: NodePath, other: NodePath) -> dict[str, object]:
    shared_depth = 0
    for left, right in zip(anchor, other):
        if left != right:
            break
        shared_depth += 1
    differing_levels = [
        index
        for index, (left, right) in enumerate(zip(anchor, other))
        if left != right
    ]
    absolute_steps = sum(abs(left - right) for left, right in zip(anchor, other))
    return {
        "path": list(other),
        "shared_prefix_depth": shared_depth,
        "differing_levels": differing_levels,
        "absolute_steps": absolute_steps,
        "same_parent": anchor[:-1] == other[:-1],
        "nearby_same_branch": anchor[:-2] == other[:-2],
        "is_adjacent_leaf": anchor[:-1] == other[:-1] and abs(anchor[-1] - other[-1]) == 1,
    }


def path_distance_map(anchor: NodePath, paths: list[NodePath]) -> list[dict[str, object]]:
    return [path_distance(anchor, path) for path in paths]


def expand_neighbor_paths(
    path: NodePath,
    radii_by_level: list[int],
    branching_factor: int,
) -> list[NodePath]:
    """Expand sibling neighborhoods at each level while preserving ancestors."""
    expanded: set[NodePath] = set()
    for level in range(len(path)):
        radius = radii_by_level[level] if level < len(radii_by_level) else radii_by_level[-1]
        prefix = path[:level]
        target = path[level]
        lower = max(0 if target == 0 else 1, target - radius)
        upper = target + radius
        for sibling in range(lower, upper + 1):
            expanded.add(prefix + (sibling,) + path[level + 1 :])
    expanded.add(path)
    return sorted(expanded)


def paths_from_manual_ranges(
    ranges: dict[int, tuple[int, int]],
    anchor: NodePath,
    branching_factor: int,
) -> list[NodePath]:
    expanded: set[NodePath] = {anchor}
    for level, bounds in ranges.items():
        if level < 0 or level >= len(anchor):
            continue
        lower = max(0 if anchor[level] == 0 else 1, bounds[0])
        upper = bounds[1]
        prefix = anchor[:level]
        suffix = anchor[level + 1 :]
        for value in range(lower, upper + 1):
            expanded.add(prefix + (value,) + suffix)
    return sorted(expanded)
