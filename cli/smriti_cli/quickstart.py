"""`smriti quickstart` — seed a curated demo space so the product clicks fast.

The empty-room problem: a fresh Smriti install opens to an empty space.
Smriti's value is emergent — it accrues as you checkpoint reasoning — so on
day one there is nothing to look at and nothing to explain why it matters.

`smriti quickstart` skips the wait. It seeds one small, finished, realistic
project — a rate-limiting feature built by two agents — captured the way
Smriti captures reasoning: decisions, the assumptions under them, a branch
that was explored and dropped, and a hand-off between agents. A new user can
then read a real continuation brief, diff a decision that diverged, and look
at coordination metrics in a few minutes instead of a few weeks.

The seeded space is named ``smriti-demo`` and is clearly marked as demo data
in its description, so it is never mistaken for the user's own work. Remove
it any time with ``smriti quickstart --remove``.

This module holds the fixture as plain structured data plus the seed/remove
logic. ``main.py`` keeps only a thin ``cmd_quickstart`` handler. The fixture
is intentionally a reduced, sanitized narrative rather than real dogfooding
history — small enough to read and maintain, representative enough to teach.
"""

from __future__ import annotations

from .client import SmritiClient, SmritiError

# ── Identity ────────────────────────────────────────────────────────────────

DEMO_SPACE_NAME = "smriti-demo"

# A sentinel embedded in the space description. `--remove` only deletes a
# space that carries this marker, so it can never delete a real space that
# happens to share the name.
DEMO_MARKER = "seeded by `smriti quickstart`"

DEMO_SPACE_DESCRIPTION = (
    f"[DEMO] Sample Smriti project — a small rate-limiting feature, "
    f"{DEMO_MARKER}. Safe to delete: smriti quickstart --remove"
)

DEMO_OBJECTIVE = "Add per-client rate limiting to the public API before the launch."

# ── Narrative building blocks ───────────────────────────────────────────────
#
# Decisions and assumptions accumulate down the checkpoint chain, the way real
# Smriti history does: each checkpoint carries the standing set forward and
# adds to it. Naming them once keeps the carry-forward honest and lets the
# divergence between `main` and the explored branch be exact.

_DEC_TOKEN_BUCKET = (
    "Use a token-bucket limiter — it absorbs our burst shape with far less "
    "per-request bookkeeping than a sliding-window log"
)
_DEC_KEY_BY_API_KEY = (
    "Key the limit on the API key, not the client IP — IPs are shared behind "
    "carrier NAT, so IP-based limits punish unrelated users"
)
_DEC_429_RETRY_AFTER = (
    "Reject over-limit requests with HTTP 429 plus a Retry-After header, so "
    "clients back off precisely instead of retrying blind"
)
_DEC_FEATURE_FLAG = (
    "Ship behind the rate_limit_enabled flag — keep it off in production "
    "until the load test passes"
)
_DEC_MONOTONIC_CLOCK = (
    "Compute token refill from a monotonic clock, not the wall clock — an NTP "
    "step was double-crediting buckets and briefly doubling a client's limit"
)
_DEC_REDIS_BUCKETS = (
    "Hold the token buckets in Redis so limits stay correct across multiple "
    "API instances"
)

_ASSUME_BURST = "Peak traffic is bursty but stays under ~800 requests/sec"
_ASSUME_SINGLE_INSTANCE = "The API runs as a single instance for now"
_ASSUME_MULTI_INSTANCE = "The API will scale to multiple instances within two quarters"


def _task(task_id: str, text: str, intent_hint: str, status: str) -> dict:
    """A structured task entry — the shape the extractor and `state` expect."""
    return {"id": task_id, "text": text, "intent_hint": intent_hint, "status": status}


# ── Main-branch checkpoints ─────────────────────────────────────────────────
#
# Four checkpoints, oldest first. They share one session and chain on `main`.
# `key` is an internal handle used to attach notes and to fork from a specific
# checkpoint — it is not sent to the backend.

MAIN_CHECKPOINTS: list[dict] = [
    {
        "key": "frame",
        "author_agent": "claude-code",
        "message": "Frame the rate-limiting work",
        "objective": DEMO_OBJECTIVE,
        "summary": (
            "The public API has no abuse protection: a single client can "
            "exhaust capacity for everyone. Surveyed the options. Two "
            "questions block any code — which algorithm, and what the limit "
            "is keyed on. No decisions yet; this checkpoint just frames the "
            "work."
        ),
        "decisions": [],
        "assumptions": [_ASSUME_BURST, _ASSUME_SINGLE_INSTANCE],
        "open_questions": [
            "Token bucket, or a sliding-window log?",
            "Do we limit per client IP, or per API key?",
        ],
        "tasks": [
            _task("survey", "Survey rate-limiting algorithms and pick candidates", "investigate", "open"),
            _task("decide", "Decide the algorithm and what the limit is keyed on", "investigate", "open"),
            _task("middleware", "Build the rate-limit middleware", "implement", "open"),
        ],
        "entities": ["public API", "API gateway", "rate limiter"],
        "artifacts": [],
    },
    {
        "key": "decide",
        "author_agent": "claude-code",
        "message": "Decide: token bucket, keyed per API key",
        "objective": DEMO_OBJECTIVE,
        "summary": (
            "Settled both open questions. Token bucket beats a sliding-window "
            "log here — it absorbs our burst shape with a fraction of the "
            "bookkeeping. The limit is keyed on the API key, not the client "
            "IP: mobile traffic shares IPs behind carrier NAT, so IP limits "
            "would punish unrelated users. Next: build the middleware."
        ),
        "decisions": [_DEC_TOKEN_BUCKET, _DEC_KEY_BY_API_KEY],
        "assumptions": [_ASSUME_BURST, _ASSUME_SINGLE_INSTANCE],
        "open_questions": [],
        "tasks": [
            _task("survey", "Survey rate-limiting algorithms and pick candidates", "investigate", "done"),
            _task("decide", "Decide the algorithm and what the limit is keyed on", "investigate", "done"),
            _task("middleware", "Build the rate-limit middleware", "implement", "open"),
            _task("loadtest", "Load-test burst and sustained traffic", "test", "open"),
        ],
        "entities": ["public API", "API gateway", "rate limiter", "API key", "token bucket"],
        "artifacts": [
            {
                "name": "Rate limit tiers",
                "content": (
                    "Free tier: 60 req/min, burst 120.\n"
                    "Pro tier: 600 req/min, burst 1200.\n"
                    "Burst window: 10s. Limits are per API key."
                ),
            }
        ],
    },
    {
        "key": "ship",
        "author_agent": "claude-code",
        "message": "Ship the limiter middleware behind a flag",
        "objective": DEMO_OBJECTIVE,
        "summary": (
            "Token-bucket middleware is in. Over-limit requests get HTTP 429 "
            "with a Retry-After header, so well-behaved clients back off "
            "instead of retrying blind. Shipped behind the rate_limit_enabled "
            "flag — it stays off in production until the load test clears it."
        ),
        "decisions": [
            _DEC_TOKEN_BUCKET,
            _DEC_KEY_BY_API_KEY,
            _DEC_429_RETRY_AFTER,
            _DEC_FEATURE_FLAG,
        ],
        "assumptions": [_ASSUME_BURST, _ASSUME_SINGLE_INSTANCE],
        "open_questions": [],
        "tasks": [
            _task("survey", "Survey rate-limiting algorithms and pick candidates", "investigate", "done"),
            _task("decide", "Decide the algorithm and what the limit is keyed on", "investigate", "done"),
            _task("middleware", "Build the rate-limit middleware", "implement", "done"),
            _task("loadtest", "Load-test burst and sustained traffic", "test", "open"),
        ],
        "entities": [
            "public API",
            "rate limiter",
            "token bucket",
            "429 response",
            "Retry-After header",
            "rate_limit_enabled flag",
        ],
        "artifacts": [
            {
                "name": "429 response contract",
                "content": (
                    "HTTP 429 Too Many Requests\n"
                    "Retry-After: <seconds>\n"
                    'Body: {"error": "rate_limited", '
                    '"retry_after_seconds": <n>, "limit": <n>}'
                ),
            }
        ],
    },
    {
        "key": "loadtest",
        "author_agent": "codex-local",
        "message": "Load test passes; fix a clock-skew refill bug",
        "objective": DEMO_OBJECTIVE,
        "summary": (
            "Picked up claude-code's middleware and ran it under load. Held "
            "750 req/sec sustained with bursts to 1500 — no false rejections. "
            "Found one real bug: token refill read the wall clock, so an NTP "
            "correction let a bucket refill twice and briefly doubled a "
            "client's allowance. Switched refill to a monotonic clock. The "
            "flag can go on."
        ),
        "decisions": [
            _DEC_TOKEN_BUCKET,
            _DEC_KEY_BY_API_KEY,
            _DEC_429_RETRY_AFTER,
            _DEC_FEATURE_FLAG,
            _DEC_MONOTONIC_CLOCK,
        ],
        "assumptions": [_ASSUME_BURST, _ASSUME_SINGLE_INSTANCE],
        "open_questions": [],
        "tasks": [
            _task("survey", "Survey rate-limiting algorithms and pick candidates", "investigate", "done"),
            _task("decide", "Decide the algorithm and what the limit is keyed on", "investigate", "done"),
            _task("middleware", "Build the rate-limit middleware", "implement", "done"),
            _task("loadtest", "Load-test burst and sustained traffic", "test", "done"),
            _task("document", "Document the 429 / Retry-After contract for API consumers", "docs", "open"),
        ],
        "entities": [
            "public API",
            "rate limiter",
            "token bucket",
            "monotonic clock",
            "load test",
        ],
        "artifacts": [],
    },
]

# ── The branch that was explored and dropped ────────────────────────────────
#
# Forked from the `decide` checkpoint. It revises the single-instance
# assumption rather than carrying it forward — that revision is the exact
# point of divergence `smriti compare` surfaces against `main`.

FORK_CHECKPOINT: dict = {
    "key": "redis-spike",
    "fork_from": "decide",
    "branch_name": "explore/redis-limiter",
    "disposition": "abandoned",
    "author_agent": "codex-local",
    "message": "Spike: a Redis-backed distributed limiter",
    "objective": DEMO_OBJECTIVE,
    "summary": (
        "Explored keeping the token buckets in Redis so limits stay correct "
        "if we ever run more than one API instance. The spike works, but it "
        "adds a hard Redis dependency and ~3ms of latency to every request. "
        "We run a single instance today, so this buys correctness we do not "
        "need yet. Parking it — revisit if we scale out."
    ),
    "decisions": [_DEC_TOKEN_BUCKET, _DEC_KEY_BY_API_KEY, _DEC_REDIS_BUCKETS],
    "assumptions": [_ASSUME_BURST, _ASSUME_MULTI_INSTANCE],
    "open_questions": ["Is ~3ms of added per-request latency acceptable at the edge?"],
    "tasks": [
        _task("survey", "Survey rate-limiting algorithms and pick candidates", "investigate", "done"),
        _task("decide", "Decide the algorithm and what the limit is keyed on", "investigate", "done"),
        _task("redis-spike", "Prototype the Redis token-bucket store", "investigate", "done"),
    ],
    "entities": ["rate limiter", "token bucket", "Redis", "distributed rate limiter"],
    "artifacts": [],
}

# ── Notes — one of each kind ─────────────────────────────────────────────────

NOTES: list[dict] = [
    {
        "checkpoint_key": "ship",
        "kind": "milestone",
        "author": "claude-code",
        "text": (
            "First working rate limiter merged. 429s with Retry-After are "
            "live behind the flag — the launch blocker is cleared pending "
            "the load test."
        ),
    },
    {
        "checkpoint_key": "decide",
        "kind": "note",
        "author": "founder",
        "text": (
            "Make the per-key limits configurable per plan tier — enterprise "
            "customers will ask for higher ceilings on day one. Do not "
            "hard-code these."
        ),
    },
    {
        "checkpoint_key": "frame",
        "kind": "noise",
        "author": "codex-local",
        "text": (
            "Renamed the scratch branch from rl-test to explore/redis-limiter "
            "so it reads cleanly in the lineage view."
        ),
    },
]

# ── Work claims — one finished, one still open ───────────────────────────────
#
# intent_type values must be in the backend's VALID_INTENT_TYPES set
# {implement, review, investigate, docs, test}; test_quickstart.py guards this.

CLAIMS: list[dict] = [
    {
        "agent": "claude-code",
        "scope": "Ship the token-bucket rate-limit middleware",
        "intent_type": "implement",
        "task_id": "middleware",
        "final_status": "done",
    },
    {
        "agent": "codex-local",
        "scope": "Document the 429 / Retry-After contract for API consumers",
        "intent_type": "docs",
        "task_id": "document",
        "final_status": "active",
    },
]

# A long TTL so the demo's one active claim stays visible as "active work"
# for the lifetime of the demo space rather than expiring in a few hours.
_DEMO_CLAIM_TTL_HOURS = 720.0


# ── Seeding ─────────────────────────────────────────────────────────────────


def _commit_payload(space_id: str, session_id: str, checkpoint: dict) -> dict:
    """Build a /api/v4/chat/commit payload from a fixture checkpoint."""
    return {
        "repo_id": space_id,
        "session_id": session_id,
        "message": checkpoint["message"],
        "summary": checkpoint.get("summary", ""),
        "objective": checkpoint.get("objective", ""),
        "decisions": checkpoint.get("decisions", []),
        "assumptions": checkpoint.get("assumptions", []),
        "tasks": checkpoint.get("tasks", []),
        "open_questions": checkpoint.get("open_questions", []),
        "entities": checkpoint.get("entities", []),
        "artifacts": checkpoint.get("artifacts", []),
        "author_agent": checkpoint["author_agent"],
    }


def _populate(client: SmritiClient, space_id: str) -> dict:
    """Write the full demo narrative into an already-created space."""
    checkpoints: dict[str, dict] = {}  # fixture key -> {id, hash, branch}

    # Main branch — one session; the four checkpoints chain on it.
    session = client.create_session(repo_id=space_id, title="smriti quickstart demo")
    main_session_id = session["id"]
    for checkpoint in MAIN_CHECKPOINTS:
        commit = client.create_chat_commit(
            _commit_payload(space_id, main_session_id, checkpoint)
        )
        checkpoints[checkpoint["key"]] = {
            "id": commit["id"],
            "hash": commit.get("commit_hash", ""),
            "branch": commit.get("branch_name", "main"),
        }

    # The branch that was explored, then dropped.
    fork_source = checkpoints[FORK_CHECKPOINT["fork_from"]]
    fork = client.fork_session(
        space_id=space_id,
        checkpoint_id=fork_source["id"],
        branch_name=FORK_CHECKPOINT["branch_name"],
    )
    branch_session_id = fork["session_id"]
    branch_name = fork.get("branch_name") or FORK_CHECKPOINT["branch_name"]
    branch_commit = client.create_chat_commit(
        _commit_payload(space_id, branch_session_id, FORK_CHECKPOINT)
    )
    checkpoints[FORK_CHECKPOINT["key"]] = {
        "id": branch_commit["id"],
        "hash": branch_commit.get("commit_hash", ""),
        "branch": branch_name,
    }
    client.close_branch(space_id, branch_name, FORK_CHECKPOINT["disposition"])

    # Notes — a milestone, a founder note, and one low-signal `noise` note.
    for note in NOTES:
        client.add_checkpoint_note(
            checkpoint_id=checkpoints[note["checkpoint_key"]]["id"],
            text=note["text"],
            author=note["author"],
            kind=note["kind"],
        )

    # Work claims — one finished, one left open so "active work" is visible.
    claims: list[dict] = []
    for spec in CLAIMS:
        claim = client.create_claim(
            space_id=space_id,
            agent=spec["agent"],
            scope=spec["scope"],
            branch_name="main",
            task_id=spec.get("task_id"),
            intent_type=spec["intent_type"],
            ttl_hours=_DEMO_CLAIM_TTL_HOURS,
        )
        if spec["final_status"] == "done":
            client.update_claim(claim["id"], "done")
        claims.append({"id": claim["id"], "status": spec["final_status"]})

    return {
        "space_id": space_id,
        "checkpoints": checkpoints,
        "branch_name": branch_name,
        "claims": claims,
    }


def seed_demo_space(client: SmritiClient) -> dict:
    """Create the `smriti-demo` space and populate it with the demo narrative.

    Returns a summary dict: ``space_id``, ``checkpoints`` (fixture key ->
    {id, hash, branch}), ``branch_name``, and ``claims``.

    If anything fails partway through, the half-built space is removed on a
    best-effort basis and the error is re-raised — so a retry always starts
    from a clean slate rather than a duplicate-name conflict.
    """
    space = client.create_space(
        name=DEMO_SPACE_NAME, description=DEMO_SPACE_DESCRIPTION
    )
    space_id = space["id"]
    try:
        return _populate(client, space_id)
    except Exception:
        try:
            # force=True: this is quickstart tearing down its own
            # half-built demo space, which may already hold checkpoints.
            client.delete_space(space_id, force=True)
        except SmritiError:
            pass  # best-effort rollback; surface the original error
        raise


# ── Lookup / removal ────────────────────────────────────────────────────────


def find_demo_space(client: SmritiClient) -> dict | None:
    """Return the `smriti-demo` space dict, or None if it does not exist."""
    try:
        return client.resolve_space(DEMO_SPACE_NAME)
    except SmritiError:
        return None


def is_demo_space(space: dict) -> bool:
    """True only for a space quickstart actually seeded.

    Guards `--remove` from ever deleting a real space that merely shares the
    `smriti-demo` name — only a space carrying the demo marker is removable.
    """
    return DEMO_MARKER in (space.get("description") or "")


def remove_demo_space(client: SmritiClient) -> dict:
    """Delete the demo space if it is safe to.

    Returns a result dict with ``removed`` (bool) and a ``reason``:
      - ``removed=True``                  — deleted
      - ``reason="no-demo-space"``        — nothing named smriti-demo exists
      - ``reason="not-a-demo-space"``     — a space exists but lacks the marker
    """
    space = find_demo_space(client)
    if space is None:
        return {"removed": False, "reason": "no-demo-space"}
    if not is_demo_space(space):
        return {
            "removed": False,
            "reason": "not-a-demo-space",
            "space_id": space["id"],
        }
    # force=True: the is_demo_space marker check above is quickstart's
    # explicit gate; the seeded demo space holds checkpoints.
    client.delete_space(space["id"], force=True)
    return {"removed": True, "space_id": space["id"]}


# ── Guided walkthrough ──────────────────────────────────────────────────────


def build_guide(seed: dict) -> list[dict]:
    """Build the post-seed walkthrough — commands with real IDs filled in."""
    checkpoints = seed["checkpoints"]
    decide_id = checkpoints["decide"]["id"]
    redis_id = checkpoints["redis-spike"]["id"]
    return [
        {
            "command": f"smriti current {DEMO_SPACE_NAME}",
            "note": "Where the project stands: direction, last milestone, what's open.",
        },
        {
            "command": f"smriti state {DEMO_SPACE_NAME}",
            "note": "The full continuation brief an agent receives at session start.",
        },
        {
            "command": f"smriti checkpoint list {DEMO_SPACE_NAME}",
            "note": "The reasoning history — five checkpoints across two agents.",
        },
        {
            "command": f"smriti compare {decide_id} {redis_id}",
            "note": "A decision that diverged: the Redis limiter explored, then dropped.",
        },
        {
            "command": f"smriti metrics {DEMO_SPACE_NAME}",
            "note": "Coordination and quality signal across the two agents.",
        },
    ]
