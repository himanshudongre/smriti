/* API client for the Smriti backend */

import type { Artifacts, ContextPack, Session, TargetTool } from '../types';

/**
 * Error thrown from any API helper on non-2xx responses.
 *
 * `detail` is the parsed `detail` field from the backend's error body when
 * it is present. Some endpoints (notably `DELETE /api/v2/commits/{id}`) return
 * structured details like `{ message, dependents }` so the UI can render a
 * second-step cascade confirmation.
 */
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function _errorMessageFromDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const msg = (detail as { message: unknown }).message;
    if (typeof msg === 'string') return msg;
  }
  return fallback;
}

const BASE_URL = '/api/v1';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = body?.detail;
    throw new ApiError(
      _errorMessageFromDetail(detail, `HTTP ${res.status}`),
      res.status,
      detail,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function createSession(
  raw_transcript: string,
  title?: string,
  source_tool?: string,
): Promise<Session> {
  return request<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ raw_transcript, title, source_tool }),
  });
}

export async function getSession(sessionId: string): Promise<Session> {
  return request<Session>(`/sessions/${sessionId}`);
}

export async function getArtifacts(sessionId: string): Promise<Artifacts> {
  return request<Artifacts>(`/sessions/${sessionId}/artifacts`);
}

export async function generateContextPack(
  sessionId: string,
  target_tool: TargetTool,
): Promise<ContextPack> {
  return request<ContextPack>(`/sessions/${sessionId}/context-packs`, {
    method: 'POST',
    body: JSON.stringify({ target_tool }),
  });
}

export async function getContextPack(packId: string): Promise<ContextPack> {
  return request<ContextPack>(`/context-packs/${packId}`);
}

// --- V2 API Methods ---

const V2_BASE_URL = '/api/v2';

async function requestV2<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${V2_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = body?.detail;
    throw new ApiError(
      _errorMessageFromDetail(detail, `HTTP ${res.status}`),
      res.status,
      detail,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function extractMemories(raw_transcript: string): Promise<import('../types').MemoryItem[]> {
  return requestV2<import('../types').MemoryItem[]>('/memory/extract', {
    method: 'POST',
    body: JSON.stringify({ raw_transcript }),
  });
}

export async function buildContextPack(
  target_tool: TargetTool,
  memory_ids: string[]
): Promise<import('../types').ContextBuildResponse> {
  return requestV2<import('../types').ContextBuildResponse>('/context/build', {
    method: 'POST',
    body: JSON.stringify({ target_tool, memory_ids }),
  });
}

export async function getMemories(type?: string, limit?: number): Promise<import('../types').MemoryItem[]> {
  const params = new URLSearchParams();
  if (type) params.append('type', type);
  if (limit) params.append('limit', limit.toString());
  const qs = params.toString() ? `?${params.toString()}` : '';
  return requestV2<import('../types').MemoryItem[]>(`/memory${qs}`);
}

export async function updateMemory(
  memoryId: string,
  payload: Partial<import('../types').MemoryItem>
): Promise<import('../types').MemoryItem> {
  return requestV2<import('../types').MemoryItem>(`/memory/${memoryId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteMemory(memoryId: string): Promise<void> {
  return requestV2<void>(`/memory/${memoryId}`, {
    method: 'DELETE',
  });
}

// --- V2 Git for Memory API ---

export async function getRepos(): Promise<import('../types').Repo[]> {
  return requestV2<import('../types').Repo[]>('/repos');
}

export async function createRepo(payload: Partial<import('../types').Repo>): Promise<import('../types').Repo> {
  return requestV2<import('../types').Repo>('/repos', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getRepo(repoId: string): Promise<import('../types').Repo> {
  return requestV2<import('../types').Repo>(`/repos/${repoId}`);
}

export async function getRepoCommits(repoId: string, branch?: string): Promise<import('../types').Commit[]> {
  const qs = branch ? `?branch=${encodeURIComponent(branch)}` : '';
  return requestV2<import('../types').Commit[]>(`/repos/${repoId}/commits${qs}`);
}

export async function getLatestCommit(repoId: string, branch = 'main'): Promise<import('../types').Commit> {
  return requestV2<import('../types').Commit>(`/repos/${repoId}/commits/latest?branch=${branch}`);
}

export async function createCommit(payload: Partial<import('../types').Commit>): Promise<import('../types').Commit> {
  return requestV2<import('../types').Commit>('/commits', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getCommit(commitId: string): Promise<import('../types').Commit> {
  return requestV2<import('../types').Commit>(`/commits/${commitId}`);
}

export async function getContextFromCommit(
  commit_id: string,
  target: TargetTool = 'generic'
): Promise<import('../types').ContextBuildResponse> {
  return requestV2<import('../types').ContextBuildResponse>('/context/from-commit', {
    method: 'POST',
    body: JSON.stringify({ commit_id, target }),
  });
}

export async function getCommitDelta(commitId: string): Promise<import('../types').CommitDelta> {
  return requestV2<import('../types').CommitDelta>(`/context/parent-delta/${commitId}`);
}

// ── V4 Chat API ────────────────────────────────────────────────────────────────

const V4_BASE_URL = '/api/v4';

async function requestV4<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${V4_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = body?.detail;
    throw new ApiError(
      _errorMessageFromDetail(detail, `HTTP ${res.status}`),
      res.status,
      detail,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function createChatSessionGeneric(
  opts: { repo_id?: string; title?: string; provider?: string; model?: string; seed_from?: string } = {}
): Promise<import('../types').ChatSession> {
  return requestV4<import('../types').ChatSession>('/chat/sessions', {
    method: 'POST',
    body: JSON.stringify(opts),
  });
}

export async function getChatSessionGeneric(sessionId: string): Promise<import('../types').ChatSession> {
  return requestV4<import('../types').ChatSession>(`/chat/sessions/${sessionId}`);
}

export async function getRecentSessionsGeneric(): Promise<import('../types').ChatSession[]> {
  return requestV4<import('../types').ChatSession[]>('/chat/sessions');
}

export async function getSessionTurnsGeneric(sessionId: string): Promise<import('../types').TurnEvent[]> {
  return requestV4<import('../types').TurnEvent[]>(`/chat/sessions/${sessionId}/turns`);
}

export async function attachSession(sessionId: string, repoId: string): Promise<import('../types').ChatSession> {
  return requestV4<import('../types').ChatSession>(`/chat/sessions/${sessionId}/attach`, {
    method: 'PUT',
    body: JSON.stringify({ repo_id: repoId }),
  });
}

// Legacy variants for debug views
export async function createChatSession(
  repoId: string,
  opts: { title?: string; provider?: string; model?: string; seed_from?: string } = {}
): Promise<import('../types').ChatSession> {
  return requestV4<import('../types').ChatSession>(`/chat/spaces/${repoId}/sessions`, {
    method: 'POST',
    body: JSON.stringify({ ...opts, repo_id: repoId }),
  });
}

export async function getChatSession(repoId: string, sessionId: string): Promise<import('../types').ChatSession> {
  return requestV4<import('../types').ChatSession>(`/chat/spaces/${repoId}/sessions/${sessionId}`);
}

export async function getSessionTurns(repoId: string, sessionId: string): Promise<import('../types').TurnEvent[]> {
  return requestV4<import('../types').TurnEvent[]>(`/chat/spaces/${repoId}/sessions/${sessionId}/turns`);
}

export async function sendChatMessage(payload: {
  session_id: string;
  repo_id?: string;
  provider: string;
  model: string;
  message: string;
  use_mock?: boolean;
  memory_scope?: string;
  mounted_checkpoint_id?: string | null;
  history_base_seq?: number | null;
}): Promise<import('../types').SendMessageResponse> {
  return requestV4<import('../types').SendMessageResponse>('/chat/send', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function generateThreadTitle(sessionId: string): Promise<import('../types').ChatSession> {
  return requestV4<import('../types').ChatSession>(`/chat/sessions/${sessionId}/title`, {
    method: 'POST',
  });
}

export async function createChatCommit(payload: {
  repo_id: string;
  session_id: string;
  message: string;
  summary?: string;
  objective?: string;
  decisions?: string[];
  assumptions?: string[];
  tasks?: string[];
  open_questions?: string[];
  entities?: string[];
  artifacts?: { id: string; type: string; label: string; content: string }[];
}): Promise<import('../types').Commit> {
  return requestV4<import('../types').Commit>('/chat/commit', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getSpaceHead(repoId: string): Promise<import('../types').HeadState> {
  return requestV4<import('../types').HeadState>(`/chat/spaces/${repoId}/head`);
}

export async function getProviderStatus(): Promise<Record<string, import('../types').ProviderStatus>> {
  return requestV4<Record<string, import('../types').ProviderStatus>>('/chat/providers');
}

// ── V5 Checkpoint API ──────────────────────────────────────────────────────────

const V5_BASE_URL = '/api/v5';

async function requestV5<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${V5_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = body?.detail;
    throw new ApiError(
      _errorMessageFromDetail(detail, `HTTP ${res.status}`),
      res.status,
      detail,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── V5 Lineage API ────────────────────────────────────────────────────────────

export async function forkSession(payload: {
  space_id: string;
  checkpoint_id: string;
  branch_name?: string;
  provider?: string;
  model?: string;
}): Promise<import('../types').ForkSessionResponse> {
  return requestV5<import('../types').ForkSessionResponse>('/lineage/sessions/fork', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getLineage(spaceId: string): Promise<import('../types').LineageResponse> {
  return requestV5<import('../types').LineageResponse>(`/lineage/spaces/${spaceId}`);
}

export async function getSpaceState(spaceId: string): Promise<import('../types').SpaceStateResponse> {
  return requestV4<import('../types').SpaceStateResponse>(`/chat/spaces/${spaceId}/state`);
}

export async function compareCheckpoints(
  aId: string,
  bId: string,
): Promise<import('../types').CompareResponse> {
  return requestV5<import('../types').CompareResponse>(
    `/lineage/checkpoints/${aId}/compare/${bId}`,
  );
}

export async function draftCheckpoint(payload: {
  session_id: string;
  num_turns?: number;
  mounted_checkpoint_id?: string | null;
  history_base_seq?: number | null;
}): Promise<{
  title: string;
  objective: string;
  summary: string;
  decisions: string[];
  assumptions: string[];
  tasks: string[];
  open_questions: string[];
  entities: string[];
}> {
  return requestV5<{
    title: string;
    objective: string;
    summary: string;
    decisions: string[];
    assumptions: string[];
    tasks: string[];
    open_questions: string[];
    entities: string[];
  }>('/checkpoint/draft', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Return the reachable checkpoint set for a session.
 *
 * For main-branch sessions: all main-branch checkpoints.
 * For forked sessions: fork-local checkpoints + fork source + ancestors.
 * Downstream main checkpoints created after the fork point are excluded.
 *
 * Use this instead of getRepoCommits() when populating the checkpoint
 * history panel or mount-candidate list inside a session.
 */
export async function getSessionCheckpoints(sessionId: string): Promise<import('../types').Commit[]> {
  return requestV5<import('../types').Commit[]>(`/lineage/sessions/${sessionId}/checkpoints`);
}

export async function reviewCheckpoint(checkpointId: string): Promise<import('../types').CheckpointReviewResponse> {
  return requestV5<import('../types').CheckpointReviewResponse>(`/checkpoint/${checkpointId}/review`, {
    method: 'POST',
  });
}

// ── Delete endpoints ─────────────────────────────────────────────────────────

/** Delete a space and cascade to all its checkpoints, sessions, and turns. */
export async function deleteRepo(repoId: string): Promise<void> {
  return requestV2<void>(`/repos/${repoId}`, { method: 'DELETE' });
}

/**
 * Delete a checkpoint. Without cascade the backend refuses with 409 if the
 * checkpoint has child commits or forked sessions, and the ApiError.detail
 * payload will contain { message, dependents } that the UI can use to render
 * a second-step cascade confirmation.
 */
export async function deleteCommit(
  commitId: string,
  opts?: { cascade?: boolean },
): Promise<void> {
  const qs = opts?.cascade ? '?cascade=true' : '';
  return requestV2<void>(`/commits/${commitId}${qs}`, { method: 'DELETE' });
}

/** Delete a chat session. Cascades to turn events; commits authored by the
 * session remain (they are owned by the space). */
export async function deleteChatSession(sessionId: string): Promise<void> {
  return requestV4<void>(`/chat/sessions/${sessionId}`, { method: 'DELETE' });
}

