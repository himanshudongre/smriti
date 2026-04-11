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

## MCP server

Run Smriti as a local MCP server so agents inside Claude Code, Cursor, or Windsurf can read and write reasoning state natively — no subprocess-shelling to the `smriti` binary.

**Installation.** Bundled with the CLI. `pip install -e ./cli` installs both `smriti` and `smriti-mcp` on your PATH.

**Claude Code config** (typically `~/.config/claude-code/mcp.json` or `~/Library/Application Support/Claude/claude_desktop_config.json` — check your host's docs for the exact path):

```json
{
  "mcpServers": {
    "smriti": {
      "command": "smriti-mcp",
      "env": { "SMRITI_API_URL": "http://localhost:8000" }
    }
  }
}
```

Restart the host and the `smriti_*` tools appear in the tool picker.

**Available tools (12):**

| Tool | Purpose |
|---|---|
| `smriti_list_spaces` | List all spaces |
| `smriti_create_space` | Create a new space |
| `smriti_delete_space` | Delete a space and all its checkpoints |
| `smriti_state` | Continuation brief for the current project state |
| `smriti_list_checkpoints` | List checkpoints in a space (optional branch filter) |
| `smriti_show_checkpoint` | Print a specific checkpoint as markdown |
| `smriti_create_checkpoint` | Create a checkpoint from freeform markdown (via extractor) |
| `smriti_review_checkpoint` | Run consistency review on a checkpoint |
| `smriti_delete_checkpoint` | Delete a checkpoint (refuses with dependents unless `cascade=true`) |
| `smriti_restore` | Print a specific checkpoint as a continuation brief |
| `smriti_fork` | Fork a new session from an existing checkpoint |
| `smriti_compare` | Structured diff between two checkpoints |

**Example.** In a Claude Code session with Smriti MCP connected, ask *"show me the current state of my-project"*. The agent calls `smriti_state(space="my-project")`, the MCP server hits the backend, pipes the result through the same `format_state_brief` formatter the CLI uses, and returns the continuation brief you'd otherwise get from `smriti state my-project` at the terminal — directly inside the chat context.

**Notes:**
- The MCP server talks to the same backend as the CLI. Keep the backend running.
- Destructive tools (`smriti_delete_space`, `smriti_delete_checkpoint`) have no per-tool confirmation prompt — the MCP host's tool-approval UI is the gate.
- `smriti_create_checkpoint` always uses the extract path. Agents pass freeform markdown and Smriti's background LLM extracts the structured fields. Pass `dry_run=True` to preview the extracted payload before committing.
- `smriti_create_checkpoint` does NOT auto-capture `project_root` (unlike the CLI, which uses cwd). MCP servers run in the host's arbitrary working directory, so cwd would plant garbage paths on every checkpoint. Pass `project_root="/absolute/path"` explicitly if you want that field populated.

**Smoke-test the server without a host.** The `mcp` SDK ships with an Inspector UI:

```bash
mcp dev smriti_cli.mcp_server:mcp
```

Opens a browser-based tool explorer connected over stdio. Click through `tools/list` (expect 12 entries, all prefixed `smriti_`) and try each tool interactively.

## Commands

```
smriti space list
smriti space create <name> [--description "..."]
smriti space delete <space> [-y]

smriti state <space>                                     # continuation brief (full artifacts by default)
smriti state <space> --preview                           # truncate artifacts to a short preview
smriti state <space> --json                              # structured output

smriti fork <checkpoint-id> [--branch <name>]            # new session from checkpoint
smriti restore <checkpoint-id>                           # brief of a specific checkpoint
smriti compare <checkpoint-a> <checkpoint-b>             # structured diff

smriti checkpoint create <space>                         # reads JSON from stdin
smriti checkpoint create <space> --from-json <path>      # from JSON file
smriti checkpoint create <space> --extract               # reads markdown, LLM extracts schema fields
smriti checkpoint create <space> --extract --dry-run     # preview the extracted payload without committing
smriti checkpoint create <space> --session <session-id>  # attach to existing session
smriti checkpoint create <space> --author-agent claude-code
smriti checkpoint create <space> --project-root /path    # override cwd auto-capture
smriti checkpoint show <checkpoint-id>
smriti checkpoint list <space>
smriti checkpoint review <checkpoint-id>
smriti checkpoint delete <checkpoint-id> [--cascade] [-y]
```

`smriti state` shows full artifact content by default — flip to `--preview` for the truncated brief.

`smriti checkpoint create` auto-captures the current working directory as the checkpoint's `project_root` so cross-agent handoffs know where the project actually lives on disk. Pass `--project-root /absolute/path` to override or `--no-project-root` to skip. Tag the checkpoint with an explicit `--author-agent <name>` (like `claude-code` or `codex-local`); without it, the backend falls back to the session's active provider.

**Extracting checkpoints from freeform agent output:** instead of hand-writing the JSON payload, pipe an agent's markdown output to `--extract` and let Smriti's background LLM extract the structured fields (decisions, assumptions, tasks, open questions, entities, artifacts) for you:

```bash
# Extract and commit in one step
cat /tmp/r3_agent_a_output.md | smriti checkpoint create my-project --extract --author-agent codex-A

# Preview what would be extracted, without committing
cat /tmp/r3_agent_a_output.md | smriti checkpoint create my-project --extract --dry-run
```

`--extract` reads stdin as freeform markdown, sends it to `POST /api/v5/checkpoint/extract`, and uses the returned fields to build the commit payload. `--dry-run` prints the extracted payload as JSON and exits without creating a checkpoint. `--extract` and `--from-json` are mutually exclusive.

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

## Multi-branch workflow

When you want to explore an alternative direction from a checkpoint without losing the main branch, fork it into a new session and write checkpoints there:

```bash
# Fork a new session off checkpoint C1
smriti fork <C1-checkpoint-id> --branch experiment

# The output gives you the new session ID. Write a checkpoint to that session:
cat <<'JSON' | smriti checkpoint create my-project --session <fork-session-id>
{
  "message": "Alternative design direction",
  "summary": "...",
  "decisions": ["Try stdlib only instead of click"]
}
JSON

# Compare the two branches
smriti compare <C1-checkpoint-id> <new-checkpoint-id>

# Read any checkpoint as a continuation brief (what you'd need to continue from it)
smriti restore <new-checkpoint-id>
```

`smriti compare` shows a structured diff with `Shared`, `Only in A`, and `Only in B` sections for decisions, assumptions, and tasks, plus the lowest common ancestor of the two checkpoints. The shared-set matching is case- and punctuation-insensitive, so two agents phrasing the same commitment differently still show up as shared.

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
| `project_root` | string | Absolute path to the project's working directory. Auto-captured by the CLI at commit time; can be overridden via the payload or `--project-root`. |
| `author_agent` | string | Agent identifier. The CLI flag `--author-agent` overrides any payload value; when unset the backend tags the checkpoint with the session's active provider. |

## Space resolution

`<space>` arguments accept either the space name or the UUID. Names are matched exactly first, then case-insensitively. If multiple spaces match, the CLI asks you to use a UUID.

## Exit codes

- `0` success
- `1` API error, invalid input, or backend unreachable
- `130` interrupted (Ctrl+C)
