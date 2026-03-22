# Smriti API Reference

This document covers the V4 (chat) and V5 (checkpoint) APIs — the current primary
interfaces. V1 and V2 endpoints are legacy and not documented here; see
[docs/legacy/](legacy/) for historical context.

Base URL: `http://localhost:8000`

All request and response bodies are JSON. All IDs are UUIDs.

---

## V4 — Chat API

Prefix: `/api/v4/chat`

The V4 API manages Sessions, Turns, and message sending. It is the primary runtime
API for the Smriti workspace.

---

### Sessions

#### Create a session

```
POST /api/v4/chat/sessions
```

Creates a new Session, optionally attached to a Space and seeded from a Checkpoint.

**Request body:**

```json
{
  "repo_id": "<space-uuid>",
  "title": "Optional title",
  "provider": "openrouter",
  "model": "anthropic/claude-3.5-sonnet",
  "seed_from": "head"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `repo_id` | UUID string | No | Attach to a Space. Omit for a FRESH session. |
| `title` | string | No | Defaults to `"Session MMM DD HH:MM"` |
| `provider` | string | No | Defaults to `chat.default_provider` from config |
| `model` | string | No | Model identifier for this provider |
| `seed_from` | string | No | `"head"` (default) seeds from latest Checkpoint; `"none"` starts fresh; a Checkpoint UUID seeds from that specific Checkpoint |

**Response:** Session object

```json
{
  "id": "uuid",
  "repo_id": "uuid or null",
  "title": "Session Mar 21 14:30",
  "active_provider": "openrouter",
  "active_model": "anthropic/claude-3.5-sonnet",
  "seeded_commit_id": "uuid or null",
  "created_at": "2026-03-21T14:30:00Z",
  "updated_at": "2026-03-21T14:30:00Z"
}
```

---

#### List recent sessions

```
GET /api/v4/chat/sessions
```

Returns the 50 most recently updated Sessions, ordered by `updated_at` descending.

**Response:** Array of Session objects

---

#### Get a session

```
GET /api/v4/chat/sessions/{session_id}
```

**Response:** Session object

---

#### Generate a session title

```
POST /api/v4/chat/sessions/{session_id}/title
```

Uses the background intelligence model to generate a concise 3–5 word title from
the first four Turns of the Session. Updates `session.title` in place.

Called automatically by the frontend after the first assistant reply (if a background
provider is configured).

**Response:** Updated Session object

---

#### List session turns

```
GET /api/v4/chat/sessions/{session_id}/turns
```

Returns all Turns for a Session, ordered by `sequence_number` ascending.

**Response:** Array of Turn objects

```json
[
  {
    "id": "uuid",
    "session_id": "uuid",
    "role": "user",
    "content": "What countries should I visit?",
    "provider": "openrouter",
    "model": "anthropic/claude-3.5-sonnet",
    "sequence_number": 0,
    "created_at": "2026-03-21T14:31:00Z"
  },
  {
    "id": "uuid",
    "session_id": "uuid",
    "role": "assistant",
    "content": "...",
    "provider": "openrouter",
    "model": "anthropic/claude-3.5-sonnet",
    "sequence_number": 1,
    "created_at": "2026-03-21T14:31:05Z"
  }
]
```

---

#### Attach a session to a space

```
PUT /api/v4/chat/sessions/{session_id}/attach
```

Attaches an existing Session to a Space. Updates `session.repo_id` and sets
`repo_id` on all existing Turns in the Session.

**Request body:**

```json
{
  "repo_id": "<space-uuid>"
}
```

**Response:** Updated Session object

---

### Sending messages

#### Send a message

```
POST /api/v4/chat/send
```

The core endpoint. Sends a user message, resolves the context based on the active
mode, calls the provider, and stores both the user Turn and assistant Turn.

**Request body:**

```json
{
  "session_id": "<session-uuid>",
  "repo_id": "<space-uuid>",
  "provider": "openai",
  "model": "gpt-4o",
  "message": "What should I do first?",
  "use_mock": false,
  "memory_scope": "latest_1",
  "mounted_checkpoint_id": null,
  "history_base_seq": null
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | UUID string | Yes | The active Session |
| `repo_id` | UUID string | No | The attached Space. Must match `session.repo_id`. |
| `provider` | string | Yes | Provider to use for this Turn |
| `model` | string | Yes | Model identifier |
| `message` | string | Yes | The user's message |
| `use_mock` | boolean | No | Use the deterministic mock adapter (no API key required) |
| `memory_scope` | string | No | `"latest_1"` (default) or `"latest_3"` |
| `mounted_checkpoint_id` | UUID string | No | If set, anchors context to this specific Checkpoint |
| `history_base_seq` | integer | No | Required when `mounted_checkpoint_id` is set. The sequence number of the last Turn before mounting. Only Turns with `sequence_number > history_base_seq` are included in context. |

**Context resolution logic:**

1. If `mounted_checkpoint_id` is set: use that Checkpoint (plus ancestors if
   `memory_scope` is `"latest_3"`). Turn history: `sequence_number > history_base_seq`.
2. If `repo_id` is set (HEAD mode): use the N most recent Checkpoints from the Space.
   Turn history: `created_at >= latest_checkpoint.created_at`.
3. Otherwise (FRESH): no Checkpoint context. No Turn history filter.

**Response:**

```json
{
  "reply": "Here is what I recommend...",
  "session_id": "uuid",
  "turn_count": 4,
  "provider": "openai",
  "model": "gpt-4o"
}
```

---

### Spaces

#### List spaces

```
GET /api/v2/repos
```

Note: Spaces use the V2 prefix. The user-facing name is "Space"; the internal
model is `RepoModel`.

**Response:** Array of Space objects

```json
[
  {
    "id": "uuid",
    "name": "Australia Trip",
    "description": "Planning for the 2026 trip",
    "created_at": "2026-03-01T10:00:00Z",
    "updated_at": "2026-03-21T14:30:00Z"
  }
]
```

#### Create a space

```
POST /api/v2/repos
```

**Request body:**

```json
{
  "name": "Australia Trip",
  "description": "Planning for the 2026 trip"
}
```

**Response:** Space object

#### Get a space

```
GET /api/v2/repos/{repo_id}
```

**Response:** Space object

#### Get space head state

```
GET /api/v4/chat/spaces/{repo_id}/head
```

Returns the latest Checkpoint and latest Session for a Space.

**Response:**

```json
{
  "repo_id": "uuid",
  "commit_hash": "abc1234...",
  "commit_id": "uuid",
  "summary": "Decided to focus on east coast cities",
  "objective": "Plan a 3-week Australia itinerary",
  "latest_session_id": "uuid",
  "latest_session_title": "Australia Trip Planning"
}
```

---

### Provider status

#### List provider status

```
GET /api/v4/chat/providers
```

Returns the configuration status of all providers. Never returns API keys.

**Response:**

```json
{
  "openai": {
    "enabled": true,
    "has_key": true,
    "missing_package": false,
    "configured": true,
    "status_label": "Ready",
    "default_model": "gpt-4o"
  },
  "anthropic": {
    "enabled": false,
    "has_key": false,
    "missing_package": false,
    "configured": false,
    "status_label": "Disabled",
    "default_model": ""
  },
  "openrouter": {
    "enabled": true,
    "has_key": true,
    "missing_package": false,
    "configured": true,
    "status_label": "Ready",
    "default_model": ""
  },
  "background_intelligence": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "enabled": true,
    "has_key": true,
    "configured": true,
    "status_label": "Ready"
  }
}
```

---

## V5 — Checkpoint API

Prefix: `/api/v5/checkpoint`

The V5 API handles checkpoint drafting — the AI-assisted extraction of structured
state from a conversation.

---

### Draft a checkpoint

```
POST /api/v5/checkpoint/draft
```

Uses the background intelligence model to extract structured metadata from the
active conversation. Returns a draft that the user can review, edit, and save.

**Important:** This endpoint respects the same context isolation as `send_message`.
If `mounted_checkpoint_id` and `history_base_seq` are provided, the draft is
extracted only from Turns after the isolation boundary — the same Turns the model
saw during the session.

**Request body:**

```json
{
  "session_id": "<session-uuid>",
  "num_turns": 15,
  "mounted_checkpoint_id": null,
  "history_base_seq": null
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | UUID string | Yes | The Session to draft from |
| `num_turns` | integer | No | Maximum number of recent Turns to include (default 15, max 100) |
| `mounted_checkpoint_id` | UUID string | No | If set, applies isolation boundary |
| `history_base_seq` | integer | No | Required when `mounted_checkpoint_id` is set |

**Turn selection:**

- If `mounted_checkpoint_id` and `history_base_seq` are both provided:
  `sequence_number > history_base_seq`, limited to `num_turns` most recent
- Otherwise: all Turns in the Session, limited to `num_turns` most recent

No previous Checkpoint context is injected into the extraction prompt. The draft
reflects only what is present in the selected Turns.

**Response:**

```json
{
  "title": "Australia East Coast Plan",
  "objective": "Decide on a 3-week itinerary for Australia focusing on the east coast",
  "summary": "The user is planning a trip to Australia and has narrowed focus to Sydney, Melbourne, and the Great Barrier Reef. Budget and timing constraints have been discussed.",
  "decisions": [
    "Focus on east coast cities only",
    "Avoid peak season (December–January)"
  ],
  "tasks": [
    "Research visa requirements",
    "Compare flight options from London"
  ],
  "open_questions": [
    "Whether to include Tasmania",
    "How many nights to allocate to each city"
  ],
  "entities": [
    "Sydney",
    "Melbourne",
    "Great Barrier Reef",
    "Qantas"
  ]
}
```

All array fields may be empty if nothing relevant was found in the conversation.
`objective` may be an empty string if the goal is not stated clearly enough to extract.

---

### Saving a checkpoint

Checkpoints are saved via the V4 commit endpoint, not V5.

```
POST /api/v4/chat/commit
```

**Request body:**

```json
{
  "repo_id": "<space-uuid>",
  "session_id": "<session-uuid>",
  "message": "Australia East Coast Plan",
  "summary": "Decided to focus on east coast...",
  "objective": "Plan a 3-week itinerary...",
  "decisions": ["Focus on east coast cities only"],
  "tasks": ["Research visa requirements"],
  "open_questions": ["Whether to include Tasmania"],
  "entities": ["Sydney", "Melbourne"]
}
```

**Response:**

```json
{
  "id": "uuid",
  "commit_hash": "abc1234def5678...",
  "message": "Australia East Coast Plan",
  "created_at": "2026-03-21T15:00:00Z"
}
```

---

### Checkpoint history

#### List checkpoints for a space

```
GET /api/v2/repos/{repo_id}/commits
```

Returns all Checkpoints for a Space, ordered by creation time.

**Response:** Array of Checkpoint objects

```json
[
  {
    "id": "uuid",
    "commit_hash": "abc1234...",
    "parent_commit_id": "uuid or null",
    "message": "Australia East Coast Plan",
    "objective": "Plan a 3-week itinerary...",
    "summary": "Decided to focus on east coast...",
    "decisions": ["Focus on east coast cities only"],
    "tasks": ["Research visa requirements"],
    "open_questions": ["Whether to include Tasmania"],
    "entities": ["Sydney", "Melbourne"],
    "created_at": "2026-03-21T15:00:00Z"
  }
]
```

#### Get a specific checkpoint

```
GET /api/v2/commits/{commit_id}
```

**Response:** Checkpoint object (full fields as above)

---

---

## V5 — Lineage API

Prefix: `/api/v5/lineage`

The Lineage API handles session forking, branch tree visualization, and checkpoint
comparison across branches.

---

### Fork a session

```
POST /api/v5/lineage/sessions/fork
```

Creates a new Session branching from a specific Checkpoint. The forked session starts
with a clean Turn history; its context comes from the checkpoint state snapshot.

**Request body:**

```json
{
  "space_id": "<space-uuid>",
  "checkpoint_id": "<checkpoint-uuid>",
  "branch_name": "my-branch",
  "provider": "openai",
  "model": "gpt-4o"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `space_id` | UUID string | Yes | The Space to fork within |
| `checkpoint_id` | UUID string | Yes | The Checkpoint to fork from |
| `branch_name` | string | No | Branch name. Defaults to `"branch-YYYY-MM-DD"` |
| `provider` | string | No | Defaults to config default |
| `model` | string | No | Model for the new session |

**Response:**

```json
{
  "session_id": "uuid",
  "branch_name": "my-branch",
  "forked_from_checkpoint_id": "uuid",
  "history_base_seq": 0
}
```

---

### Get branch tree

```
GET /api/v5/lineage/spaces/{space_id}
```

Returns all Checkpoints and Sessions for a Space, structured for branch tree
rendering. Checkpoints carry `parent_checkpoint_id` for the commit ancestry chain;
Sessions carry `forked_from_checkpoint_id` to locate where each branch began.

**Response:**

```json
{
  "space_id": "uuid",
  "checkpoints": [
    {
      "id": "uuid",
      "commit_hash": "abc1234...",
      "message": "Australia East Coast Plan",
      "branch_name": "main",
      "parent_checkpoint_id": "uuid or null",
      "created_at": "...",
      "summary": "...",
      "objective": "..."
    }
  ],
  "sessions": [
    {
      "id": "uuid",
      "title": "Session Mar 21",
      "branch_name": "main",
      "forked_from_checkpoint_id": "uuid or null",
      "seeded_commit_id": "uuid or null",
      "created_at": "..."
    }
  ]
}
```

---

### Compare two checkpoints

```
GET /api/v5/lineage/checkpoints/{a_id}/compare/{b_id}
```

Returns a structured diff of two Checkpoint state snapshots. Works across any two
Checkpoints regardless of branch origin.

**Response:**

```json
{
  "checkpoint_a": {
    "id": "uuid",
    "commit_hash": "abc1234...",
    "message": "...",
    "branch_name": "main",
    "summary": "...",
    "objective": "...",
    "decisions": ["..."],
    "tasks": ["..."],
    "open_questions": ["..."]
  },
  "checkpoint_b": { ... },
  "diff": {
    "summary_a": "...",
    "summary_b": "...",
    "objective_a": "...",
    "objective_b": "...",
    "decisions_only_a": ["..."],
    "decisions_only_b": ["..."],
    "decisions_shared": ["..."],
    "tasks_only_a": ["..."],
    "tasks_only_b": ["..."],
    "tasks_shared": ["..."]
  }
}
```

---

### Get reachable checkpoints for a session

```
GET /api/v5/lineage/sessions/{session_id}/checkpoints
```

Returns the Checkpoint set reachable from a given Session. This is the authoritative
query for populating the checkpoint history panel and mount-candidate list.

Reachability rules:

- **Main-branch session** — all Checkpoints where `branch_name == "main"`, newest first.
- **Forked session** — fork-local Checkpoints (same branch) plus the fork-source
  Checkpoint and all its ancestors. Downstream main Checkpoints created after the fork
  point are explicitly excluded.

**Response:** Array of full Checkpoint objects (same schema as `GET /api/v2/commits/{id}`)

---

## Error responses

All endpoints return errors in this format:

```json
{
  "detail": "Session not found"
}
```

| Status | Meaning |
|---|---|
| 400 | Bad request — missing required field or invalid input |
| 404 | Resource not found |
| 422 | Validation error — request body did not match schema |
| 500 | Server error — typically a misconfigured or missing background provider |
| 502 | Provider error — the upstream LLM returned an error or invalid response |

---

## Notes on legacy endpoints

`/api/v1` — Transcript paste ingestion. Accepts raw text, extracts memories,
generates context packs. Not used by the current UI. Retained for compatibility.

`/api/v2` — Agent-push model (repos, commits, context packs). Partially reused by
the current UI for Space CRUD and Checkpoint retrieval, but the agent-push workflow
it was designed for is no longer the primary interaction model.

Do not build new integrations against V1 or V2.
