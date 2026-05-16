from __future__ import annotations

import argparse
import json
import random
import shutil
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .agents import DeepSeekJsonAgent, DeterministicDemoAgent, JsonAgent, OpenAIJsonAgent
from .cli import load_config
from .config import WorldGeneratorConfig
from .generator import WorldGenerator
from .ids import path_label
from .storage import WorldStore
from .story import StorySessionManager


STATIC_ROOT = Path(__file__).with_name("web_static")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Story world visual web runner.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config_path = args.config

    class Handler(StoryWorldWebHandler):
        default_config_path = config_path

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"Story Agent visual runner listening at {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


class StoryWorldWebHandler(SimpleHTTPRequestHandler):
    default_config_path: Path | None = None

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self._serve_static("index.html")
            return
        if self.path.startswith("/static/"):
            self._serve_static(unquote(self.path.removeprefix("/static/")))
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/worlds":
                self._write_json(self._list_worlds())
                return
            if parsed.path == "/api/world":
                query = parse_qs(parsed.query)
                self._write_json(self._world_detail(query.get("world_id", [""])[0]))
                return
            if parsed.path == "/api/session":
                query = parse_qs(parsed.query)
                self._write_json(self._load_session(query.get("session_id", [""])[0]))
                return
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        try:
            if self.path == "/api/start":
                self._write_json(self._start_story(self._read_json()))
                return
            if self.path == "/api/begin":
                self._write_json(self._begin_story(self._read_json()))
                return
            if self.path == "/api/choose":
                self._write_json(self._submit_choice(self._read_json()))
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/world":
                query = parse_qs(parsed.query)
                self._write_json(self._delete_world(query.get("world_id", [""])[0]))
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _serve_static(self, relative_path: str) -> None:
        path = (STATIC_ROOT / relative_path).resolve()
        if not path.is_file() or STATIC_ROOT.resolve() not in path.parents:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(path.suffix, "application/octet-stream")
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _list_worlds(self) -> dict[str, Any]:
        config = load_config(self.default_config_path)
        root = Path(config.runtime.worlds_root)
        worlds = []
        for world_dir in sorted(root.iterdir()) if root.exists() else []:
            manifest_path = world_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            store = WorldStore(root, world_dir.name)
            manifest = store.load_manifest()
            world_config = manifest.get("config", {})
            worlds.append(
                {
                    "world_id": manifest.get("world_id", world_dir.name),
                    "prompt": self._display_world_prompt(manifest.get("prompt", "")),
                    "display_name": self._world_display_name(manifest),
                    "scale": self._scale_from_config(world_config),
                    "story_count": len(store.list_sessions()),
                    "token_usage": store.load_usage().get("totals", {}),
                }
            )
        return {"worlds": worlds}

    def _world_detail(self, world_id: str) -> dict[str, Any]:
        if not world_id:
            raise ValueError("world_id is required")
        config = load_config(self.default_config_path)
        root = Path(config.runtime.worlds_root)
        store = WorldStore(root, world_id)
        manifest = store.load_manifest()
        sessions = sorted(store.list_sessions(), key=lambda item: item.get("story_number", 0))
        return {
            "world": {
                "world_id": manifest["world_id"],
                "prompt": self._display_world_prompt(manifest.get("prompt", "")),
                "display_name": self._world_display_name(manifest),
                "bootstrap": manifest.get("bootstrap", {}),
                "scale": self._scale_from_config(manifest.get("config", {})),
                "token_usage": store.load_usage().get("totals", {}),
            },
            "stories": [self._session_summary(session) for session in sessions],
        }

    def _delete_world(self, world_id: str) -> dict[str, Any]:
        if not world_id:
            raise ValueError("world_id is required")
        config = load_config(self.default_config_path)
        root = Path(config.runtime.worlds_root).resolve()
        target = (root / world_id).resolve()
        if root not in target.parents or not target.exists():
            raise FileNotFoundError(f"World not found: {world_id}")
        if not (target / "manifest.json").exists():
            raise ValueError(f"Refusing to delete non-world directory: {world_id}")
        shutil.rmtree(target)
        return {"deleted": True, "world_id": world_id}

    def _load_session(self, session_id: str) -> dict[str, Any]:
        if not session_id:
            raise ValueError("session_id is required")
        config = self._config_for_session(session_id, {})
        manager = StorySessionManager(
            agent=DeterministicDemoAgent(),
            config=config,
            runtime_root=Path(config.runtime.worlds_root),
        )
        return {"story": self._compact_story_result(manager.load(session_id=session_id))}

    def _start_story(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._config_from_payload(payload)
        runtime_root = Path(config.runtime.worlds_root)

        default_random_world = not (payload.get("prompt") or "").strip()
        prompt = payload.get("prompt") or "童话风格的架空世界"
        world_id = payload.get("world_id")
        default_random_protagonist = not (payload.get("protagonist") or "").strip()
        protagonist = payload.get("protagonist") or "随机身份的主角"
        others = payload.get("others") or "生成2到4个其它人物。"
        generation_requirements = payload.get("generation_requirements") or config.story.generation_requirements
        story_length_mode = payload.get("story_length_mode") or config.story.story_length_mode

        if world_id:
            manifest = WorldStore(runtime_root, world_id).load_manifest()
            world = manifest
            prompt = manifest["prompt"]
            config = WorldGeneratorConfig.from_dict(manifest["config"])
            config.story.generation_requirements = generation_requirements
            config.story.story_length_mode = story_length_mode
            if payload.get("debug_story_agent_input") is not None:
                config.story.debug_story_agent_input = bool(payload["debug_story_agent_input"])
        else:
            self._apply_world_scale(config, payload.get("world_scale"))
            if default_random_world or default_random_protagonist:
                self._apply_random_generation_guardrails(
                    config,
                    randomize_world=default_random_world,
                    randomize_protagonist=default_random_protagonist,
                )
        selected_agent, selected_model = self._agent_selection(
            payload,
            config,
            default_agent="deepseek",
            default_model="deepseek-chat",
        )
        self._log_agent_selection("/api/start", payload, selected_agent, selected_model)
        config.agent.default_agent = selected_agent
        config.agent.model = selected_model
        agent = self._agent_from_payload(
            {"agent": selected_agent, "model": selected_model},
            config,
            default_agent="deepseek",
            default_model="deepseek-chat",
        )
        generator = WorldGenerator(agent=agent, config=config, runtime_root=runtime_root)
        manager = StorySessionManager(agent=agent, config=config, runtime_root=runtime_root)
        time_id = path_label(self._random_path(config.history_depth + 1, config.history_default_branching))
        space_id = path_label(self._random_path(config.space_depth + 1, config.space_default_branching))
        if not world_id:
            world = generator.create_world(prompt)
        initialization = generator.initialize_context(
            world_id=world["world_id"],
            user_prompt=prompt,
            history_path=time_id,
            space_path=space_id,
        )
        result = manager.start(
            world_id=world["world_id"],
            history_path=time_id,
            space_path=space_id,
            protagonist_prompt=protagonist,
            other_characters_prompt=others,
            generation_requirements=generation_requirements,
            story_length_mode=story_length_mode,
            agent_selection={"agent": selected_agent, "model": selected_model},
            generate_first_segment=False,
        )
        return {
            "world": {
                "world_id": world["world_id"],
                "prompt": self._display_world_prompt(world["prompt"]),
                "display_name": self._world_display_name(world),
                "bootstrap": world["bootstrap"],
            },
            "initialization": {
                "random_history_path": list(initialization["current_history_path"]),
                "random_space_path": list(initialization["current_space_path"]),
                "history_paths_initialized": initialization["history_paths_initialized"],
                "space_paths_initialized": initialization["space_paths_initialized"],
            },
            "story": self._compact_story_result(result),
        }

    def _begin_story(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._config_for_session(payload["session_id"], payload)
        agent_payload = self._agent_payload_for_session(payload["session_id"], payload, config)
        selected_agent, selected_model = self._agent_selection(
            agent_payload,
            config,
            default_agent="deepseek",
            default_model="deepseek-chat",
        )
        self._log_agent_selection("/api/begin", payload, selected_agent, selected_model)
        agent = self._agent_from_payload(agent_payload, config, default_agent="deepseek", default_model="deepseek-chat")
        manager = StorySessionManager(
            agent=agent,
            config=config,
            runtime_root=Path(config.runtime.worlds_root),
        )
        result = manager.begin_story(session_id=payload["session_id"])
        return {"story": self._compact_story_result(result)}

    def _submit_choice(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._config_for_session(payload["session_id"], payload)
        agent_payload = self._agent_payload_for_session(payload["session_id"], payload, config)
        selected_agent, selected_model = self._agent_selection(
            agent_payload,
            config,
            default_agent="deepseek",
            default_model="deepseek-chat",
        )
        self._log_agent_selection("/api/choose", payload, selected_agent, selected_model)
        agent = self._agent_from_payload(agent_payload, config, default_agent="deepseek", default_model="deepseek-chat")
        manager = StorySessionManager(
            agent=agent,
            config=config,
            runtime_root=Path(config.runtime.worlds_root),
        )
        result = manager.submit_choice(
            session_id=payload["session_id"],
            choice_id=payload.get("choice_id") or "USER",
            choice_text=payload.get("choice_text") or "",
        )
        return {"story": self._compact_story_result(result)}

    def _config_from_payload(self, payload: dict[str, Any]) -> WorldGeneratorConfig:
        config = load_config(self.default_config_path)
        if payload.get("world_requirements"):
            config.world_generation.personal_requirements = payload["world_requirements"]
        if payload.get("generation_requirements"):
            config.story.generation_requirements = payload["generation_requirements"]
        if payload.get("story_length_mode"):
            config.story.story_length_mode = payload["story_length_mode"]
        if payload.get("debug_story_agent_input") is not None:
            config.story.debug_story_agent_input = bool(payload["debug_story_agent_input"])
        return config

    def _apply_random_generation_guardrails(
        self,
        config: WorldGeneratorConfig,
        *,
        randomize_world: bool,
        randomize_protagonist: bool,
    ) -> None:
        notes = []
        if randomize_world:
            notes.append(
                "随机世界必须生成与常见默认套路明显不同的新世界；"
                "不要复用矿区、矿石能源、雾海、雾城、晶体、晶化病、晶能、潮历、星潮历、潮镜、林雾、林雾辞、年轻译记员、测潮师学徒等旧套路关键词。"
            )
        if randomize_protagonist:
            notes.append(
                "随机主角的身份、姓名、能力、职业和牵涉的矛盾都要重新发明，避免复用林雾/林雾辞式人物，也避免默认写矿工、晶体研究者、雾中幸存者、年轻学徒或记录员。"
            )
        if not notes:
            return
        base = config.world_generation.personal_requirements.strip()
        config.world_generation.personal_requirements = "；".join([part for part in [base, *notes] if part])

    def _config_for_session(self, session_id: str, payload: dict[str, Any]) -> WorldGeneratorConfig:
        fallback = self._config_from_payload(payload)
        runtime_root = Path(fallback.runtime.worlds_root)
        for world_dir in runtime_root.iterdir() if runtime_root.exists() else []:
            store = WorldStore(runtime_root, world_dir.name)
            session_path = store.sessions_dir / f"{session_id}.json"
            if not session_path.exists():
                continue
            config = WorldGeneratorConfig.from_dict(store.load_manifest()["config"])
            if payload.get("generation_requirements"):
                config.story.generation_requirements = payload["generation_requirements"]
            if payload.get("debug_story_agent_input") is not None:
                config.story.debug_story_agent_input = bool(payload["debug_story_agent_input"])
            return config
        return fallback

    def _agent_payload_for_session(
        self,
        session_id: str,
        payload: dict[str, Any],
        config: WorldGeneratorConfig,
    ) -> dict[str, Any]:
        stored = self._stored_agent_selection(session_id, config)
        if stored:
            return {**payload, **stored}
        selected_agent, selected_model = self._agent_selection(
            payload,
            config,
            default_agent="deepseek",
            default_model="deepseek-chat",
        )
        return {**payload, "agent": selected_agent, "model": selected_model}

    def _stored_agent_selection(self, session_id: str, config: WorldGeneratorConfig) -> dict[str, str]:
        runtime_root = Path(config.runtime.worlds_root)
        for world_dir in runtime_root.iterdir() if runtime_root.exists() else []:
            store = WorldStore(runtime_root, world_dir.name)
            session_path = store.sessions_dir / f"{session_id}.json"
            if not session_path.exists():
                continue
            session = store.load_session(session_id)
            stored = session.get("agent_selection") or {}
            selected_agent = stored.get("agent")
            selected_model = stored.get("model")
            if selected_agent and selected_model:
                return {"agent": selected_agent, "model": selected_model}
        return {}

    def _apply_world_scale(self, config: WorldGeneratorConfig, scale: str | None) -> None:
        levels_by_scale = {"small": 2, "medium": 3, "large": 4}
        levels = levels_by_scale.get((scale or "large").strip().lower())
        if levels is None:
            return
        config.history_depth = levels - 1
        config.space_depth = levels - 1

    def _agent_from_payload(
        self,
        payload: dict[str, Any],
        config: WorldGeneratorConfig,
        *,
        default_agent: str | None = None,
        default_model: str | None = None,
    ) -> JsonAgent:
        selected, model = self._agent_selection(payload, config, default_agent=default_agent, default_model=default_model)
        self._raise_generation_randomness(config)
        if selected == "openai":
            try:
                return OpenAIJsonAgent(
                    model=model,
                    reasoning_effort=config.agent.reasoning_effort,
                    temperature=config.agent.temperature,
                    top_p=config.agent.top_p,
                )
            except ModuleNotFoundError as exc:
                if exc.name == "openai":
                    raise RuntimeError(
                        "当前环境未安装 openai Python 包。请先安装项目依赖或执行："
                        "python3 -m pip install openai。"
                    ) from exc
                raise
        if selected == "deepseek":
            try:
                return DeepSeekJsonAgent(
                    model=model if model.startswith("deepseek-") else "deepseek-chat",
                    temperature=config.agent.temperature,
                    top_p=config.agent.top_p,
                )
            except ModuleNotFoundError as exc:
                if exc.name == "openai":
                    raise RuntimeError(
                        "当前环境未安装 openai Python 包，DeepSeek 兼容接口也需要该客户端。请先安装项目依赖或执行："
                        "python3 -m pip install openai。"
                    ) from exc
                raise
        return DeterministicDemoAgent()

    def _raise_generation_randomness(self, config: WorldGeneratorConfig) -> None:
        config.agent.temperature = max(float(config.agent.temperature or 0), 1.2)
        config.agent.top_p = max(float(config.agent.top_p or 0), 0.98)

    def _agent_selection(
        self,
        payload: dict[str, Any],
        config: WorldGeneratorConfig,
        *,
        default_agent: str | None = None,
        default_model: str | None = None,
    ) -> tuple[str, str]:
        selected = (payload.get("agent") or default_agent or config.agent.default_agent or "demo").strip().lower()
        model = (payload.get("model") or default_model or config.agent.model or "").strip()
        if model.startswith("deepseek-"):
            selected = "deepseek"
        if selected == "deepseek":
            model = model if model.startswith("deepseek-") else "deepseek-chat"
        elif selected == "openai":
            model = model if model and not model.startswith("deepseek-") else "gpt-5.5"
        return selected, model

    def _log_agent_selection(
        self,
        route: str,
        payload: dict[str, Any],
        selected_agent: str,
        selected_model: str,
    ) -> None:
        requested_agent = payload.get("agent") or "<missing>"
        requested_model = payload.get("model") or "<missing>"
        print(
            f"{route} requested agent={requested_agent} model={requested_model}; "
            f"using agent={selected_agent} model={selected_model}",
            flush=True,
        )

    def _random_path(self, depth: int, branching_factor: int) -> tuple[int, ...]:
        upper = max(1, branching_factor)
        return tuple(random.randint(1, upper) for _ in range(depth))

    def _compact_story_result(self, result: dict[str, Any]) -> dict[str, Any]:
        session = result["session"]
        output = result.get("output") or {}
        ending = result.get("ending") or session.get("ending")
        collected = result["collected_context"]
        manager_notes = collected.get("manager_notes", {})
        current = collected.get("current", {})
        nearby = collected.get("nearby", {})
        other_characters = collected.get("other_characters", [])
        active_ids = manager_notes.get("active_characters") or [
            item.get("id") for item in other_characters if item.get("active")
        ]
        story_segments = [
            {
                "turn": index,
                "story": segment.get("story", ""),
                "new_events": segment.get("new_events", []),
                "state_notes": segment.get("state_notes", ""),
                "user_input_after_segment": self._choice_for_turn(session, index),
            }
            for index, segment in enumerate(session.get("story_outputs") or [])
        ]
        story_text = self._full_story_text(session) if ending else output.get("story", "")
        return {
            "session_id": session["session_id"],
            "story_number": session.get("story_number"),
            "world_id": session["world_id"],
            "interaction_count": session["interaction_count"],
            "ended": bool(session.get("ended")),
            "started": bool(session.get("story_outputs")),
            "story_length_mode": session.get("story_length_mode", "long"),
            "ending_policy": session.get("ending_policy", {}),
            "agent_selection": session.get("agent_selection", {}),
            "history_path": session["history_path"],
            "space_path": session["space_path"],
            "intro": result.get("intro"),
            "story": story_text,
            "story_segments": story_segments,
            "choices": [] if ending else output.get("choices", []),
            "new_events": output.get("new_events", []),
            "ending": ending,
            "state_notes": output.get("state_notes"),
            "usage": output.get("usage"),
            "token_usage": self._token_usage(session),
            "manager_notes": manager_notes,
            "current": {
                "history": self._node_summary(current.get("history")),
                "space": self._node_summary(current.get("space")),
            },
            "nearby_counts": {
                "history": len(nearby.get("history", [])),
                "space": len(nearby.get("space", [])),
            },
            "characters": {
                "protagonist": collected.get("protagonist"),
                "others": other_characters,
                "active_ids": active_ids,
                "departed": manager_notes.get("departed_characters", []),
                "joined": manager_notes.get("joined_characters", []),
            },
            "events": {
                "current_time_events": collected.get("current_time_events", []),
                "current_time_event_groups": collected.get("current_time_event_groups", {}),
                "all_event_summary": collected.get("all_event_summary", []),
            },
        }

    def _full_story_text(self, session: dict[str, Any]) -> str:
        parts = [
            segment.get("story", "").strip()
            for segment in session.get("story_outputs") or []
            if segment.get("story", "").strip()
        ]
        ending = session.get("ending") or {}
        if ending.get("ending"):
            parts.append(ending["ending"].strip())
        return "\n\n".join(parts)

    def _choice_for_turn(self, session: dict[str, Any], turn: int) -> dict[str, Any] | None:
        for choice in session.get("choices", []):
            if choice.get("turn") == turn:
                return choice
        return None

    def _token_usage(self, session: dict[str, Any]) -> dict[str, Any]:
        session_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        payloads = []
        if session.get("intro"):
            payloads.append(session["intro"])
        payloads.extend(session.get("story_outputs") or [])
        if session.get("ending"):
            payloads.append(session["ending"])
        for payload in payloads:
            usage = payload.get("usage") or {}
            for key in session_totals:
                session_totals[key] += int(usage.get(key, 0) or 0)
        world_totals = WorldStore(Path(self._config_from_payload({}).runtime.worlds_root), session["world_id"]).load_usage().get("totals", {})
        return {
            "session": session_totals,
            "world": {
                "input_tokens": int(world_totals.get("input_tokens", 0) or 0),
                "output_tokens": int(world_totals.get("output_tokens", 0) or 0),
                "total_tokens": int(world_totals.get("total_tokens", 0) or 0),
            },
        }

    def _node_summary(self, node: dict[str, Any] | None) -> dict[str, Any] | None:
        if not node:
            return None
        return {
            "path": node.get("path"),
            "name": node.get("name") or node.get("calendar"),
            "summary": node.get("summary"),
            "status": node.get("status"),
            "retention": node.get("retention"),
        }

    @staticmethod
    def _display_world_prompt(prompt: str) -> str:
        return prompt.strip().rstrip("。；; ")

    @staticmethod
    def _world_display_name(manifest: dict[str, Any]) -> str:
        prompt = StoryWorldWebHandler._display_world_prompt(manifest.get("prompt", ""))
        world_id = manifest.get("world_id", "")
        if not prompt:
            return f"未命名世界 {str(world_id)[:6]}".strip()
        if prompt == "随机的架空世界":
            return f"{prompt} {str(world_id)[:6]}".strip()
        return prompt

    def _session_summary(self, session: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id": session.get("session_id"),
            "story_number": session.get("story_number"),
            "interaction_count": session.get("interaction_count", 0),
            "started": bool(session.get("story_outputs")),
            "ended": bool(session.get("ended")),
            "story_length_mode": session.get("story_length_mode", "long"),
            "title": self._story_title(session),
            "token_usage": self._session_token_usage(session),
        }

    def _story_title(self, session: dict[str, Any]) -> str:
        ending = session.get("ending") or {}
        if ending.get("final_state"):
            return ending["final_state"]
        if session.get("story_outputs"):
            latest = session["story_outputs"][-1]
            return latest.get("state_notes") or (latest.get("story", "")[:40] + "...")
        intro = session.get("intro") or {}
        return intro.get("intro", "")[:48] + ("..." if len(intro.get("intro", "")) > 48 else "")

    def _session_token_usage(self, session: dict[str, Any]) -> dict[str, int]:
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        payloads = []
        if session.get("intro"):
            payloads.append(session["intro"])
        payloads.extend(session.get("story_outputs") or [])
        if session.get("ending"):
            payloads.append(session["ending"])
        for payload in payloads:
            usage = payload.get("usage") or {}
            for key in totals:
                totals[key] += int(usage.get(key, 0) or 0)
        return totals

    def _scale_from_config(self, config: dict[str, Any]) -> str:
        levels = int(config.get("history_depth", 3) or 3) + 1
        return {2: "small", 3: "medium", 4: "large"}.get(levels, "large")


if __name__ == "__main__":
    main()
