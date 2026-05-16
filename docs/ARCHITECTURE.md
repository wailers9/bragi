# Project Architecture

This project is organized around a small set of explicit runtime responsibilities:

1. create and store a world foundation,
2. materialize time and space nodes on demand,
3. collect story-ready context,
4. maintain characters and story state,
5. ask JSON agents to fill only the data they own.

## Runtime Flow

```text
CLI
  -> WorldGenerator
       -> world bootstrap agent
       -> history/space initialization agents
       -> WorldStore
  -> StorySessionManager
       -> update time/space
       -> update character roster
       -> InformationCollector
       -> story agent
       -> WorldStore
```

The CLI and web runner are entrypoints. They should not contain business rules
beyond request/argument parsing, config loading, response shaping, and wiring the
selected agent implementation.

## Module Responsibilities

### `agents.py`

Defines the JSON agent interface and implementations:

- `JsonAgent`: protocol used by the rest of the project.
- `AgentResult`: dict payload plus token usage.
- `DeterministicDemoAgent`: local deterministic test/demo agent.
- `OpenAIJsonAgent`: Responses API backed agent, imported lazily so local tests do
  not require the OpenAI package.

No story, storage, or state-management logic should live here.

### `config.py`

Contains typed runtime configuration. This is where behavior knobs belong:

- model and runtime root,
- world generation requirements,
- story update cadence,
- character detail/context probabilities,
- character departure and arrival probabilities,
- world depth and neighborhood expansion.

Config defaults should stay conservative and runnable with the demo agent.

### `ids.py`

Owns numeric path parsing and path math:

- parse comma/dot paths,
- format path labels,
- pad paths to configured depth,
- compute ancestor template paths,
- expand nearby sibling paths.

Path rules should be implemented here instead of scattered through storage or
story code.

### `storage.py`

Owns all filesystem layout and index maintenance through `WorldStore`.

Current structure:

```text
runtime/worlds/<world_id>/
  manifest.json
  index.json
  usage.json
  history/<time ancestors...>/node.json
  history/<current time...>/space/<space ancestors...>/node.json
  space/<global space template ancestors...>/node.json
  characters/<character_id>.json
  sessions/<session_id>.json
  events/<history_path>.json
  debug/
```

Callers should use `WorldStore` methods rather than constructing these paths
directly.

### `generator.py`

Owns world creation and time/space materialization:

- creates `manifest.json`,
- creates first-level time and global space templates,
- initializes the current history node and nearby history summaries,
- initializes the current time-scoped space node and nearby space summaries,
- enriches summary history/space nodes into full nodes,
- records agent usage.

`WorldGenerator` does not write story prose and does not decide protagonist
choices.

When a current history node is initialized, its `ongoing_events.public_events`
and `ongoing_events.personal_events` are also copied into the event store as
initial current-time events. This makes them available to story and character
agents through the collector.

### `context.py`

Builds a compact world context for downstream agents:

- world prompt/bootstrap/config,
- current full history and space node,
- nearby initialized history and space summaries,
- index counts.

This module reads storage but should not mutate it.

### `collector.py`

Builds the complete story-agent input by combining:

- world context from `StoryContextBuilder`,
- protagonist and other characters,
- probabilistically included character details,
- current time events,
- grouped current-time public/personal/story events,
- all event summaries,
- manager notes,
- story phase.

This is the final gate before the story agent receives context.

### `characters.py`

Owns character lifecycle:

- initial protagonist and other character creation,
- per-character independent departure rolls,
- relationship-weighted retention,
- probabilistic new character arrival,
- calling the character addition agent,
- active roster summaries for the story manager.

Character changes are reported back to `StorySessionManager`, which forwards the
important notice to the story agent.

### `story.py`

Owns interactive session state:

- session creation,
- choice submission,
- independent time and space update counters,
- time/space update probability,
- initialization of newly reached time/space,
- character roster updates,
- story agent calls,
- event append operations.

If time/space or characters change, this module adds explicit manager notes so
the story agent must explain the change in prose.

### `prompts.py`

Contains all prompt templates and prompt builder functions. Prompts should:

- state the agent role and ownership boundary,
- include enough context for the agent to do that job,
- forbid schema-external fields,
- describe null/summary/full-node behavior clearly,
- keep schema examples aligned with `schemas.py`.

### `schemas.py`

Contains strict JSON schemas for agent outputs. Any prompt output format change
must be reflected here, and vice versa.

### `cli.py`

Provides command-line workflows:

- create/init demo world,
- enrich history or space,
- build context,
- initialize characters,
- start and continue story sessions,
- one-command play loop.

CLI commands should call service classes rather than duplicating their logic.

### `web.py` and `web_static/`

Provide the local visual runner. The backend uses only Python's standard HTTP
server and exposes:

- `GET /`: black-and-white web UI,
- `POST /api/start`: create world, initialize context, start story,
- `POST /api/choose`: submit optional user direction and continue.

The frontend visualizes story text, free-form direction input, current time/space paths, node
summaries, characters, events, and manager notices. It should remain a thin
presentation layer over `WorldGenerator` and `StorySessionManager`.

## Agent Boundaries

Each agent has a narrow output ownership:

- World agent: only world foundation and high-level time/space structures.
- History init agent: requested history nodes only.
- Space init agent: requested space nodes under the current time only.
- Enrichment agents: one existing node, upgraded to full detail.
- Character init agent: protagonist and initial other characters.
- Character addition agent: new `other` characters only.
- Intro agent: a pre-story introduction, known-world facts, and unresolved mysteries.
- Story agent: story prose, free-form user direction handling, new events, state notes.

Agents should not silently create data outside their schema or ownership.

## Important State Notices

The story agent receives manager notes for important state changes:

- `critical_story_notice`: time or space changed.
- `critical_character_notice`: old characters left or new characters joined.

When these notices indicate a change, the story agent must explain it naturally
in the next segment and must use the new current time/space and active roster.

## Information Refresh

After each submitted choice, `StorySessionManager` updates session paths first.
Then `InformationCollector` is called with the updated `history_path`,
`space_path`, and `interaction_count`.

This means every new story segment sees:

- the current history node for the updated time path,
- the current time-scoped space node for the updated space path,
- current-time events from the updated history path,
- grouped public/personal/story events,
- the latest character roster after departures and arrivals,
- active character ids from the roster update,
- a fresh random consistency sample seeded by world, current paths, interaction
  count, and event count.

Path distance metadata is included in context as `path_distance_rule` and
`path_distance`. Agents should treat longer shared prefixes as closer
time/space relationships, same parent plus leaf difference of 1 as adjacent, and
earlier-level differences as larger-scale distance.

## Testing Strategy

The current tests cover:

- path parsing and neighbor expansion,
- prompt config and required prompt constraints,
- nested time and time-scoped space storage,
- context building,
- story flow,
- time/space update and initialization,
- character departure/arrival and story-agent notices.

Prefer adding focused tests around lifecycle behavior before refactoring module
boundaries.
