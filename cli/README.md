# smriti-cli

Command-line access to Smriti's reasoning-state backend. Built for coding agents and scripts — pipe JSON in, get readable markdown out.

## Install

From the repo root:

```bash
cd cli
pip install -e .
```

This installs a `smriti` command on your PATH.

## Configuration

Set the backend URL via env var (defaults to `http://localhost:8000`):

```bash
export SMRITI_API_URL=http://localhost:8000
```

Or pass `--api-url` on any command.

## Commands

```
smriti space list
smriti space create <name> [--description "..."]

smriti state <space>                                     # continuation brief
smriti state <space> --full-artifacts                    # include full artifacts
smriti state <space> --json                              # structured output

smriti checkpoint create <space>                         # reads JSON from stdin
smriti checkpoint create <space> --from-json <path>      # from file
smriti checkpoint show <checkpoint-id>
smriti checkpoint list <space>
smriti checkpoint review <checkpoint-id>
```

Every command supports `--json` for structured output.

## Typical agent workflow

Read current project state:

```bash
smriti state my-project
```

Write a checkpoint from a JSON object piped on stdin:

```bash
cat <<'JSON' | smriti checkpoint create my-project
{
  "message": "Decided to use Pydantic for state validation",
  "objective": "Build runtime-enforced state layer",
  "summary": "...",
  "decisions": ["Use Pydantic BaseModel for state", "extra=forbid blocks injection"],
  "assumptions": ["Latency cost is acceptable"],
  "tasks": ["Benchmark validation overhead"],
  "open_questions": ["How to handle shared state across agents"],
  "entities": ["Pydantic", "BaseModel"],
  "artifacts": [
    {"id": "a1", "type": "text", "label": "Draft implementation", "content": "..."}
  ]
}
JSON
```

Review a specific checkpoint for consistency issues:

```bash
smriti checkpoint review <checkpoint-id>
```

## Checkpoint payload schema

Only `message` is required. Every other field defaults to empty.

| Field | Type | Notes |
|---|---|---|
| `message` | string | Short title (required) |
| `objective` | string | What you are working toward |
| `summary` | string | Narrative of what was figured out |
| `decisions` | string[] | Explicit choices made |
| `assumptions` | string[] | Things taken for granted |
| `tasks` | string[] | Concrete action items |
| `open_questions` | string[] | Unresolved issues |
| `entities` | string[] | Key concepts, tools, names |
| `artifacts` | object[] | `{id, type, label, content}` entries |

## Space resolution

`<space>` arguments accept either the space name or the UUID. Names are matched exactly first, then case-insensitively. If multiple spaces match, the CLI asks you to use a UUID.

## Exit codes

- `0` success
- `1` API error, invalid input, or backend unreachable
- `130` interrupted (Ctrl+C)
