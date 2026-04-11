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
- **Protocol version.** The `mcp` SDK negotiates the protocol version on its own during the `initialize` handshake — you get whatever the installed `mcp` package and your host agree on, and that's fine. No Smriti code pins a version.
- **Logging.** The SDK logs `Processing request of type …` at INFO on every tool call. `smriti-mcp` defaults the `mcp` logger to `WARNING` so host log panels stay readable. Set `SMRITI_MCP_LOG_LEVEL=INFO` (or `DEBUG`) in the host's MCP env block when you need to debug a transport issue.

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

## Using Smriti from a coding agent

Smriti is designed to be driven by a coding agent inside its tool loop — either by shelling out to `smriti` from any host, or by calling the `smriti_*` MCP tools directly (Claude Code, Cursor, Windsurf). The workflow is the same in both modes, and the rest of this section is transport-agnostic — CLI commands and their MCP equivalents are shown side by side. The shape was validated across five rounds of dogfood testing with real cross-agent handoffs.

The pattern is always:

1. **Orient.** Read the current state of the space before doing anything.
2. **Work.** Do whatever the task requires. Smriti has no opinion about what happens between checkpoints.
3. **Checkpoint.** Write a structured snapshot at each inflection point.
4. **Hand off.** The next agent reads the new state and continues.

### 1. Orient

```bash
smriti state my-project
```

From an MCP host, the agent calls `smriti_state(space="my-project")`. Either way you get the same markdown brief — objective, summary, decisions, assumptions, tasks, open questions, and full artifact content — rendered into the agent's context. This is the minimum set of facts the next agent needs to continue work.

For a list of past checkpoints (with full UUIDs so you can feed them back into fork / compare / restore):

```bash
smriti checkpoint list my-project
```

MCP equivalent: `smriti_list_checkpoints(space="my-project")`.

### 2. Checkpoint at each inflection point

In early rounds of dogfood, agents had to hand-write JSON payloads. From V3 onward, the preferred path is freeform markdown through the LLM extractor — pass the same kind of note you'd leave a teammate and Smriti pulls out the structured fields:

```bash
cat <<'MD' | smriti checkpoint create my-project --extract --author-agent claude-code
# Decided on Pydantic for the state validation layer

After trying dataclass-based validation and hitting the injection-attack
surface from unbounded extra fields, going with Pydantic BaseModel and
`extra="forbid"`. Latency overhead is ~0.3 ms per call, well under budget.

## Open questions
- How do we share state across parallel agent runs?
- Cleaner schema-versioning story for migrations?

## Artifacts
- Draft implementation: see `state_layer.py`
MD
```

`--extract` posts the markdown to `/api/v5/checkpoint/extract`, gets back the structured fields, and commits. Add `--dry-run` to preview the extraction without writing anything:

```bash
cat /tmp/handoff.md | smriti checkpoint create my-project --extract --dry-run
```

The CLI auto-captures `$(pwd)` as the checkpoint's `project_root` so the next agent knows where the project lives on disk. Override with `--project-root /absolute/path` or skip with `--no-project-root`. Tag the author with `--author-agent claude-code` / `--author-agent codex-local` so space history attributes each checkpoint to the agent that wrote it.

MCP equivalent — agent calls `smriti_create_checkpoint(space="my-project", content="# Decided on Pydantic ...", author_agent="claude-code")`. The MCP server runs the same extract → commit pipeline. Note that MCP does **not** auto-capture `project_root` (the MCP server lives in the host's arbitrary cwd); pass `project_root="/absolute/path"` explicitly when you want the field populated.

Review a checkpoint for consistency before handing it off:

```bash
smriti checkpoint review <checkpoint-id>
```

Surfaces possible contradictions, hidden assumptions, already-resolved open questions, and unused entities. MCP equivalent: `smriti_review_checkpoint(checkpoint_id="<id>")`.

### 3. Hand off to the next agent

A second agent (different process, different model family, different session) starts fresh. It runs `smriti state my-project` — or calls `smriti_state` from inside its MCP host — and receives the same brief the first agent just wrote. There is no prose handoff, no pasting markdown between windows, no re-explaining. The agent picks up where the previous one left off and continues working.

This is the core loop. Rounds 3 through 5 of dogfood testing exercised exactly this pattern across Claude Code ↔ Codex handoffs, same-family Codex ↔ Codex handoffs, and a round 5 end-to-end test that drove all 12 MCP tools from a host-less Python client. The shape holds.

## Branching when you want to explore an alternative

Sometimes an agent wants to try a different direction without losing the main line. Fork from any checkpoint into a new session on its own branch:

```bash
# Fork a new session off checkpoint C1
smriti fork <C1-checkpoint-id> --branch alternative-design

# Output gives you a new session UUID. Write a checkpoint into it:
cat alternative.md | smriti checkpoint create my-project \
    --extract --session <fork-session-id> --author-agent codex-local

# Compare the two branches
smriti compare <C1-checkpoint-id> <fork-checkpoint-id>

# Pull any checkpoint back into context as a continuation brief
smriti restore <fork-checkpoint-id>
```

`smriti compare` shows the common ancestor, per-side objectives / summaries, and `Shared` / `Only in A` / `Only in B` splits for decisions, assumptions, and tasks. The shared-set matching is case- and punctuation-insensitive, so two agents phrasing the same commitment differently still show up as shared.

`smriti restore` renders a specific checkpoint in the same shape as `smriti state`, so the agent reads it and continues as if that checkpoint were current HEAD.

MCP equivalents: `smriti_fork(checkpoint_id="<C1>", branch="alternative-design")`, `smriti_create_checkpoint(..., session="<fork-session-id>")`, `smriti_compare(checkpoint_a="<A>", checkpoint_b="<B>")`, `smriti_restore(checkpoint_id="<id>")`. The same four tools, the same four operations, no host-specific glue.

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
