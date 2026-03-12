# Agent Hub

Agent Hub is a framework-style platform for building, running, and iterating on custom agents without having to hand-roll agent wiring, runtime orchestration, or UI integration from scratch.

It gives you a stable runtime in `src/core/`, a shared authoring workspace in `src/workspace/`, a FastAPI backend, and a React UI. The main goal is to reduce the complexity of defining agents and tools: you add an agent, tool, or markdown skill in the workspace, and the platform discovers it and makes it available through the API and UI.

## Features

- Simple agent authoring with Python classes and a shared contract layer.
- Simple tool authoring with explicit metadata and live progress events.
- Markdown-based skills for reusable behavior and knowledge.
- Runtime discovery of workspace agents, tools, and skills.
- Direct and orchestrated execution modes.
- Streaming assistant, tool, and thinking events in the UI.
- Shared conversation persistence and user-scoped uploaded knowledge.

## Documentation

- [PROJECT.md](./PROJECT.md) for the higher-level project overview and repository layout.
- [src/core/README.md](./src/core/README.md) for core runtime architecture.
- [src/workspace/README.md](./src/workspace/README.md) for agent, tool, and skill authoring.

## Prerequisites

- Python 3.9+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 18+

## Environment

Create a repo-root [`.env`](./.env) file.

Required for the default Gemini setup:

```env
GOOGLE_API_KEY=your_google_ai_studio_key
```

Optional model overrides:

```env
MODEL_NAME=gemini-3.1-flash-lite-preview
MODEL_BACKEND=litellm
EMBEDDING_PROVIDER=google
EMBEDDING_MODEL=text-embedding-004
```

Notes:
- `GOOGLE_API_KEY` is required for the default native Gemini path.
- If you route through LiteLLM, also set the provider-specific key for that model, such as `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
- Embedding sync and semantic retrieval read `EMBEDDING_PROVIDER` and `EMBEDDING_MODEL` from the environment. The offline `uv run poe embeddings-sync` command now loads the repo `.env` automatically.
- After changing environment variables, restart `uv run poe dev` or `uv run poe backend`.

## Install

Install Python dependencies:

```bash
uv sync --all-groups --all-extras
```

Install frontend dependencies:

```bash
uv run poe frontend-install
```

## How It Works

Agent Hub keeps the framework runtime and the workspace content separate:

- `src/core/` owns discovery, execution, streaming, memory, and platform behavior.
- `src/workspace/` owns the agents, tools, and skills you define.

That split means contributors can focus on defining agents and tools with the provided contracts instead of wiring their own runtime loop, event streaming, or registry plumbing.

## Run Locally

Start backend + frontend together:

```bash
uv run poe dev
```

Stop the dev supervisor:

```bash
uv run poe stop
```

Run backend only:

```bash
uv run poe backend
```

Run frontend only:

```bash
uv run poe frontend
```

Local URLs:
- App: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)

`poe dev` and `poe stop` use the Python supervisor in [`scripts/dev_supervisor.py`](./scripts/dev_supervisor.py), so startup and shutdown do not depend on shell-specific job control.

## Common Commands

- Run tests: `uv run poe test`
- Format code: `uv run poe format`
- Start the agent scaffold wizard: `uv run poe new-agent`
  - Under the hood this runs `uv run python scripts/create_agent_scaffold.py`
- Build frontend: `npm --prefix frontend run build`
- Install the VS Code Related Tests extension: `uv run poe install-tests-ext`

## CLI Entrypoint

The local API/CLI entrypoint is [`src/api.py`](./src/api.py).

Examples:

```bash
uv run python src/api.py list
uv run python src/api.py catalog
uv run python src/api.py chat "summarize the refund policy"
uv run python src/api.py repl
```

The agent scaffold wizard lives in [`scripts/create_agent_scaffold.py`](./scripts/create_agent_scaffold.py). It is deterministic, does not call a model, and can create a starter agent module plus optional matching skill and tool stubs. The wizard asks for a namespace path like `support/refunds`, then derives the module filename from the agent name.
