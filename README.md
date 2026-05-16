# Story Agent Project

This repository starts with a configurable fictional world generator. It is
designed so a later story generator can request nearby time periods and nearby
locations by numeric path, while only materializing files that are actually
initialized.

## Core Ideas

- Numeric paths identify nested world-space and world-history nodes.
- Prompt templates are built with Python `str.format(...)`.
- World structure depth, history depth, neighborhood expansion, and nested field
  defaults are configured in one place.
- Detailed node files are created only after explicit or automatic initialization.
- The exact current time node and current place node are always retained in full.

For module boundaries and runtime flow, see [Project Architecture](docs/ARCHITECTURE.md).

## Quick Start

```bash
python -m story_world.cli init-demo \
  --prompt "随机的架空世界" \
  --time-id 2,5,3,3 \
  --space-id 2,1,1,1
```

The demo command uses a deterministic local agent so the workflow can run
without an external API.

## Visual Runner

Run the black-and-white local web UI:

```bash
PYTHONPATH=src python3 -m story_world.web --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

The page can create a world, initialize time/space and characters, generate the
current story segment, submit optional user direction, and visualize current paths, node
summaries, character changes, event updates, and manager notices. The visual
runner randomly generates the initial time and space paths from the configured
depth and branching values.

To use the real GPT agent:

```bash
export OPENAI_API_KEY="..."
python3 -m pip install openai
python -m story_world.cli init-demo \
  --agent openai \
  --prompt "随机的架空世界" \
  --time-id 2,5,3,3 \
  --space-id 2,1,1,1
```

`OpenAIJsonAgent` uses the Responses API with strict JSON Schema output. The
default OpenAI model is `gpt-5.5`; the model can be overridden with
`--model` or `config/worldgen.json`.

The CLI automatically loads `config/worldgen.json` when `--config` is omitted.
The main tweakable runtime values now live there:

```json
{
  "agent": {
    "default_agent": "demo",
    "model": "gpt-5.5",
    "reasoning_effort": null
  },
  "runtime": {
    "worlds_root": "runtime/worlds"
  },
  "world_generation": {
    "personal_requirements": "富有想象力，有趣地构造一个架空世界。"
  },
  "story": {
    "generation_requirements": "随机创作风格。"
  }
}
```

## Enrich Initialized Nodes

Initialization creates nearby summary nodes plus one full current node. A later
story step can expand any initialized summary node on demand:

```bash
python -m story_world.cli enrich-history \
  --agent openai \
  --world-id "<world_id>" \
  --prompt "随机的架空世界" \
  --time-id 2,5,3,4

python -m story_world.cli enrich-space \
  --agent openai \
  --world-id "<world_id>" \
  --prompt "随机的架空世界" \
  --space-id 2,1,1,2
```

Each enrichment call reads the saved summary node, asks the agent to complete it
without contradicting existing facts, merges the result, and rewrites that node
with `retention: "full"`.

## Token Usage

Every agent call records usage under:

```text
runtime/worlds/<world_id>/usage.json
```

The file tracks:

- per-call input/output/total tokens
- cumulative totals for the world

## World Index And Story Context

Each world now maintains:

```text
runtime/worlds/<world_id>/index.json
```

The index tracks all materialized time and space nodes plus their lifecycle state:

- `summary`
- `full`
- `pending_agent_completion`

Time nodes are stored as nested folders. A path such as `1,3,3,3` is stored under:

```text
runtime/worlds/<world_id>/history/1.0.0.0/1.3.0.0/1.3.3.0/1.3.3.3/node.json
```

Space nodes are scoped to the current time node. A space path such as `1,2,2,2`
inside that time is stored under:

```text
runtime/worlds/<world_id>/history/1.0.0.0/1.3.0.0/1.3.3.0/1.3.3.3/space/1.0.0.0/1.2.0.0/1.2.2.0/1.2.2.2/node.json
```

You can build story-ready context with:

```bash
python -m story_world.cli build-context \
  --world-id "<world_id>" \
  --time-id 2,5,3,3 \
  --space-id 2,1,1,1
```

The context bundle includes:

- world bootstrap data
- current full history node
- current full space node
- nearby initialized history summaries
- nearby initialized space summaries
- index counts for total/full nodes

## Characters And Story Loop

Characters are stored under:

```text
runtime/worlds/<world_id>/characters/
```

Each character includes:

- `role`: `protagonist` or `other`
- `summary`
- `detail`
- `relationships`
- `active`

Initialize characters:

```bash
python -m story_world.cli init-characters \
  --world-id "<world_id>" \
  --time-id 2,5,3,3 \
  --space-id 2,1,1,1 \
  --protagonist "随机身份的主角"
```

When `--protagonist` is passed to `init-demo`, character initialization runs
immediately after the current time and place are initialized:

```bash
python -m story_world.cli init-demo \
  --prompt "随机的架空世界" \
  --time-id 2,5,3,3 \
  --space-id 2,1,1,1 \
  --protagonist "随机身份的主角" \
  --world-requirements "底层规则简单易懂，避免表层题材限制"
```

Start a story session:

```bash
python -m story_world.cli story-start \
  --world-id "<world_id>" \
  --time-id 2,5,3,3 \
  --space-id 2,1,1,1 \
  --protagonist "随机身份的主角" \
  --generation-requirements "随机创作风格。"
```

Submit optional user direction and continue:

```bash
python -m story_world.cli story-choose \
  --session-id "<session_id>" \
  --choice-text "调查异常"
```

The story manager collects:

- protagonist detail
- current time and place detail
- world overview, world rules, space summary, history summary
- other character summaries and probabilistic details based on closeness
- random existing time/place records for continuity
- current time events and all event summaries
- initialized public/personal events from the current history node
- latest protagonist choice and manager state notes

Before the first interactive story segment, a separate intro agent writes a
short introduction that gives readers a broad sense of the world while keeping
key mysteries unresolved.

Generated story events are appended under:

```text
runtime/worlds/<world_id>/events/<history_path>.json
```

Time and place update cadence is configured with named presets:

```json
{
  "story": {
    "update_cadence": "normal",
    "update_cadences": {
      "slower": {"base_probability": 0.02, "growth_per_turn": 0.04, "max_probability": 0.45},
      "normal": {"base_probability": 0.05, "growth_per_turn": 0.08, "max_probability": 0.65},
      "faster": {"base_probability": 0.12, "growth_per_turn": 0.12, "max_probability": 0.85}
    }
  }
}
```

Time and place keep separate `turns_since_*_update` counters. When time updates,
only the time counter resets; when place updates, only the place counter resets.
The default `normal` preset makes updates uncommon in the first few choices and
reasonably likely around the fifth choice.

## One-command Play

Start a new playable session:

```bash
python -m story_world.cli play \
  --agent openai \
  --model gpt-5.5 \
  --prompt "随机的架空世界" \
  --protagonist "随机身份的主角" \
  --world-requirements "底层规则简单易懂，避免表层题材限制" \
  --generation-requirements "随机创作风格。"
```

Continue the same session after choosing:

```bash
python -m story_world.cli play \
  --agent deepseek \
  --model deepseek-chat \
  --session-id "<session_id>" \
  --choice-text "提交税制影响分析初稿"
```

By default `play` prints a compact result with `world_id`, `session_id`, story
text, new events, and usage, then stays open for free-form direction input.
Enter `q` to quit. Add `--once` to generate one segment and exit, or `--full`
to print the full collected context.

Story length and debugging are configurable:

```json
{
  "story": {
    "min_story_chars": 1000,
    "debug_story_agent_input": true,
    "print_story_agent_input": false
  }
}
```

When `debug_story_agent_input` is true, every prompt sent to the story Agent is
saved under:

```text
runtime/worlds/<world_id>/debug/story_agent_input_turn_0000.txt
```

Use `--print-story-agent-input` if you also want the full story-Agent prompt
printed in the terminal.

Generated runtime files are written under:

```text
runtime/worlds/<world_id>/
```

First-level time and global space template folders are created when a world is
created. Deeper current and nearby nodes appear as initialization reaches them.
