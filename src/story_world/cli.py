from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from .agents import DeepSeekJsonAgent, DeterministicDemoAgent, OpenAIJsonAgent
from .config import WorldGeneratorConfig
from .context import StoryContextBuilder
from .generator import WorldGenerator
from .characters import CharacterManager
from .story import StorySessionManager
from .ids import path_label


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fictional world generator demo CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_demo = sub.add_parser("init-demo", help="Create a demo world and initialize one context.")
    init_demo.add_argument("--prompt", required=True)
    init_demo.add_argument("--time-id", required=True)
    init_demo.add_argument("--space-id", required=True)
    init_demo.add_argument("--protagonist")
    init_demo.add_argument("--others", default="生成2到4个其它人物。")
    init_demo.add_argument("--world-requirements")
    init_demo.add_argument("--config", type=Path)
    init_demo.add_argument("--agent", choices=["demo", "openai", "deepseek"])
    init_demo.add_argument("--model")

    enrich_history = sub.add_parser("enrich-history", help="Expand one initialized history node.")
    enrich_history.add_argument("--world-id", required=True)
    enrich_history.add_argument("--prompt", required=True)
    enrich_history.add_argument("--time-id", required=True)
    enrich_history.add_argument("--config", type=Path)
    enrich_history.add_argument("--agent", choices=["demo", "openai", "deepseek"])
    enrich_history.add_argument("--model")

    enrich_space = sub.add_parser("enrich-space", help="Expand one initialized space node.")
    enrich_space.add_argument("--world-id", required=True)
    enrich_space.add_argument("--prompt", required=True)
    enrich_space.add_argument("--space-id", required=True)
    enrich_space.add_argument("--config", type=Path)
    enrich_space.add_argument("--agent", choices=["demo", "openai", "deepseek"])
    enrich_space.add_argument("--model")

    build_context = sub.add_parser("build-context", help="Build story-ready world context.")
    build_context.add_argument("--world-id", required=True)
    build_context.add_argument("--time-id", required=True)
    build_context.add_argument("--space-id", required=True)
    build_context.add_argument("--config", type=Path)

    init_characters = sub.add_parser("init-characters", help="Initialize protagonist and other characters.")
    init_characters.add_argument("--world-id", required=True)
    init_characters.add_argument("--time-id", required=True)
    init_characters.add_argument("--space-id", required=True)
    init_characters.add_argument("--protagonist", required=True)
    init_characters.add_argument("--others", default="生成2到4个其它人物。")
    init_characters.add_argument("--config", type=Path)
    init_characters.add_argument("--agent", choices=["demo", "openai", "deepseek"])
    init_characters.add_argument("--model")

    story_start = sub.add_parser("story-start", help="Start an interactive story session.")
    story_start.add_argument("--world-id", required=True)
    story_start.add_argument("--time-id", required=True)
    story_start.add_argument("--space-id", required=True)
    story_start.add_argument("--protagonist", required=True)
    story_start.add_argument("--others", default="生成2到4个其它人物。")
    story_start.add_argument("--generation-requirements")
    story_start.add_argument("--story-length-mode", choices=["normal", "long", "infinite"])
    story_start.add_argument("--language-style", help=argparse.SUPPRESS)
    story_start.add_argument("--config", type=Path)
    story_start.add_argument("--agent", choices=["demo", "openai", "deepseek"])
    story_start.add_argument("--model")

    story_choose = sub.add_parser("story-choose", help="Submit optional user direction and continue story.")
    story_choose.add_argument("--session-id", required=True)
    story_choose.add_argument("--choice-id", default="USER", help=argparse.SUPPRESS)
    story_choose.add_argument("--choice-text", help="Optional user direction. Leave empty to continue directly.")
    story_choose.add_argument("--config", type=Path)
    story_choose.add_argument("--agent", choices=["demo", "openai", "deepseek"])
    story_choose.add_argument("--model")

    play = sub.add_parser("play", help="One-command playable story entrypoint.")
    play.add_argument("--prompt", help="World prompt for a new play session.")
    play.add_argument("--world-id", help="Existing world id to start a new story in.")
    play.add_argument("--time-id")
    play.add_argument("--space-id")
    play.add_argument("--protagonist", default="随机身份的主角")
    play.add_argument("--others", default="生成2到4个其它人物。")
    play.add_argument("--world-requirements")
    play.add_argument("--generation-requirements")
    play.add_argument("--story-length-mode", choices=["normal", "long", "infinite"], default="long")
    play.add_argument("--language-style", help=argparse.SUPPRESS)
    play.add_argument("--session-id", help="Existing session id to continue.")
    play.add_argument("--choice-id", help=argparse.SUPPRESS)
    play.add_argument("--choice-text", help="Optional user direction when continuing an existing session.")
    play.add_argument("--full", action="store_true", help="Print full internal context instead of compact output.")
    play.add_argument("--once", action="store_true", help="Run one segment and exit instead of interactive loop.")
    play.add_argument("--print-story-agent-input", action="store_true", help="Print every story-agent prompt for debugging.")
    play.add_argument("--config", type=Path)
    play.add_argument("--agent", choices=["demo", "openai", "deepseek"])
    play.add_argument("--model")
    return parser


def load_config(path: Path | None) -> WorldGeneratorConfig:
    if path is None:
        default_path = Path("config/worldgen.json")
        if default_path.exists():
            return WorldGeneratorConfig.from_dict(json.loads(default_path.read_text(encoding="utf-8")))
        return WorldGeneratorConfig()
    return WorldGeneratorConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(args.config)
    if getattr(args, "world_requirements", None) is not None:
        config.world_generation.personal_requirements = args.world_requirements
    if getattr(args, "print_story_agent_input", False):
        config.story.print_story_agent_input = True
    if args.command == "build-context":
        builder = StoryContextBuilder(runtime_root=Path(config.runtime.worlds_root))
        result = builder.build(
            world_id=args.world_id,
            history_path=args.time_id,
            space_path=args.space_id,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    selected_agent = args.agent or config.agent.default_agent
    if selected_agent == "openai":
        agent = OpenAIJsonAgent(
            model=args.model or config.agent.model,
            reasoning_effort=config.agent.reasoning_effort,
            temperature=config.agent.temperature,
            top_p=config.agent.top_p,
        )
    elif selected_agent == "deepseek":
        agent = DeepSeekJsonAgent(
            model=args.model or "deepseek-chat",
            temperature=config.agent.temperature,
            top_p=config.agent.top_p,
        )
    else:
        agent = DeterministicDemoAgent()
    generator = WorldGenerator(
        agent=agent,
        config=config,
        runtime_root=Path(config.runtime.worlds_root),
    )

    if args.command == "init-demo":
        world = generator.create_world(args.prompt)
        result = generator.initialize_context(
            world_id=world["world_id"],
            user_prompt=args.prompt,
            history_path=args.time_id,
            space_path=args.space_id,
            protagonist_prompt=args.protagonist,
            other_characters_prompt=args.others,
        )
        print(json.dumps({"world": world, "initialization": result}, ensure_ascii=False, indent=2))
    elif args.command == "enrich-history":
        result = generator.enrich_history_node(
            world_id=args.world_id,
            user_prompt=args.prompt,
            history_path=args.time_id,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "enrich-space":
        result = generator.enrich_space_node(
            world_id=args.world_id,
            user_prompt=args.prompt,
            space_path=args.space_id,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "init-characters":
        manager = CharacterManager(agent=agent, runtime_root=Path(config.runtime.worlds_root), config=config)
        result = manager.initialize_characters(
            world_id=args.world_id,
            history_path=args.time_id,
            space_path=args.space_id,
            protagonist_prompt=args.protagonist,
            other_characters_prompt=args.others,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "story-start":
        manager = StorySessionManager(
            agent=agent,
            config=config,
            runtime_root=Path(config.runtime.worlds_root),
        )
        result = manager.start(
            world_id=args.world_id,
            history_path=args.time_id,
            space_path=args.space_id,
            protagonist_prompt=args.protagonist,
            other_characters_prompt=args.others,
            generation_requirements=args.generation_requirements or args.language_style,
            story_length_mode=args.story_length_mode,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "story-choose":
        manager = StorySessionManager(
            agent=agent,
            config=config,
            runtime_root=Path(config.runtime.worlds_root),
        )
        result = manager.submit_choice(
            session_id=args.session_id,
            choice_id=args.choice_id,
            choice_text=args.choice_text,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "play":
        manager = StorySessionManager(
            agent=agent,
            config=config,
            runtime_root=Path(config.runtime.worlds_root),
        )
        if args.session_id:
            if args.choice_text is None and not args.choice_id:
                result = interactive_continue(manager, args.session_id, args.full)
                return
            print("[play] submitting user direction and generating next story segment...", file=sys.stderr, flush=True)
            result = manager.submit_choice(
                session_id=args.session_id,
                choice_id=args.choice_id or ("USER" if args.choice_text else "CONTINUE"),
                choice_text=args.choice_text,
            )
            print(json.dumps(result if args.full else compact_story_result(result), ensure_ascii=False, indent=2))
            if not args.once:
                interactive_loop(manager, result, args.full)
            return

        if not args.prompt and not args.world_id:
            raise SystemExit("--prompt is required when starting a new play session")
        if args.world_id:
            from .storage import WorldStore

            world = WorldStore(Path(config.runtime.worlds_root), args.world_id).load_manifest()
            prompt = world["prompt"]
            print(f"[play] starting a new story in world_id={args.world_id}...", file=sys.stderr, flush=True)
        else:
            prompt = args.prompt
            print("[play] creating world bootstrap...", file=sys.stderr, flush=True)
            world = generator.create_world(prompt)
        time_id = args.time_id or random_path(config.history_depth + 1, config.history_default_branching)
        space_id = args.space_id or random_path(config.space_depth + 1, config.space_default_branching)
        print(f"[play] world_id={world['world_id']} created; initializing time/place/characters...", file=sys.stderr, flush=True)
        initialization = generator.initialize_context(
            world_id=world["world_id"],
            user_prompt=prompt,
            history_path=time_id,
            space_path=space_id,
        )
        print("[play] initialization complete; generating first story segment...", file=sys.stderr, flush=True)
        result = manager.start(
            world_id=world["world_id"],
            history_path=time_id,
            space_path=space_id,
            protagonist_prompt=args.protagonist,
            other_characters_prompt=args.others,
            generation_requirements=args.generation_requirements or args.language_style,
            story_length_mode=args.story_length_mode,
        )
        print("[play] story segment complete.", file=sys.stderr, flush=True)
        payload = {
            "world": world,
            "initialization": initialization,
            "story": result,
        }
        print(json.dumps(payload if args.full else compact_play_result(payload), ensure_ascii=False, indent=2))
        if not args.once:
            interactive_loop(manager, result, args.full)


def compact_story_result(result: dict) -> dict:
    session = result["session"]
    output = result.get("output") or {}
    ending = result.get("ending") or session.get("ending")
    return {
        "session_id": session["session_id"],
        "story_number": session.get("story_number"),
        "world_id": session["world_id"],
        "history_path": session["history_path"],
        "space_path": session["space_path"],
        "interaction_count": session["interaction_count"],
        "ended": bool(session.get("ended")),
        "intro": result.get("intro"),
        "story": output.get("story") or (ending or {}).get("ending", ""),
        "choices": [] if ending else output.get("choices", []),
        "new_events": output.get("new_events", []),
        "ending": ending,
        "usage": output.get("usage") or (ending or {}).get("usage"),
    }


def compact_play_result(payload: dict) -> dict:
    story = compact_story_result(payload["story"])
    return {
        "world_id": payload["world"]["world_id"],
        "session_id": story["session_id"],
        "story_number": story.get("story_number"),
        "history_path": story["history_path"],
        "space_path": story["space_path"],
        "intro": story.get("intro"),
        "story": story["story"],
        "choices": story["choices"],
        "new_events": story["new_events"],
        "usage": {
            "initialization": payload["initialization"].get("usage", {}),
            "story": story["usage"],
        },
    }


def interactive_continue(manager: StorySessionManager, session_id: str, full: bool) -> None:
    result = None
    print(f"[play] continuing session {session_id}. Enter a direction, empty to continue, or q to quit.", file=sys.stderr, flush=True)
    interactive_loop(manager, result, full, session_id=session_id)


def interactive_loop(
    manager: StorySessionManager,
    result: dict | None,
    full: bool,
    session_id: str | None = None,
) -> None:
    current_session_id = session_id or (result["session"]["session_id"] if result else None)
    while True:
        choice_text = input("下一步导向（直接回车推进，q 退出）: ").strip()
        if choice_text.lower() in {"q", "quit", "exit"}:
            print("[play] exited.", file=sys.stderr, flush=True)
            return
        print("[play] generating next story segment...", file=sys.stderr, flush=True)
        result = manager.submit_choice(
            session_id=current_session_id,
            choice_id="USER" if choice_text else "CONTINUE",
            choice_text=choice_text,
        )
        current_session_id = result["session"]["session_id"]
        print(json.dumps(result if full else compact_story_result(result), ensure_ascii=False, indent=2))
        if result["session"].get("ended"):
            print("[play] story ended.", file=sys.stderr, flush=True)
            return


def random_path(depth: int, branching_factor: int) -> str:
    upper = max(1, branching_factor)
    return path_label(tuple(random.randint(1, upper) for _ in range(depth)))


if __name__ == "__main__":
    main()
