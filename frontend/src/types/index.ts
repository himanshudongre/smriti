/* Session and artifact types matching backend schemas */

export interface Session {
  id: string;
  title: string | null;
  source_tool: string | null;
  status: 'processing' | 'completed' | 'failed';
  raw_transcript: string;
  created_at: string;
}

export interface Decision {
  description: string;
  context: string;
}

export interface Task {
  description: string;
  status: string;
}

export interface OpenQuestion {
  question: string;
  context: string;
}

export interface Entity {
  name: string;
  type: string;
  context: string;
}

export interface CodeSnippet {
  language: string;
  code: string;
  description: string;
}

export interface Artifacts {
  summary: string;
  decisions: Decision[];
  tasks: Task[];
  open_questions: OpenQuestion[];
  entities: Entity[];
  code_snippets: CodeSnippet[];
}

export interface ContextPack {
  id: string;
  session_id: string;
  target_tool: string;
  content: string;
  format: string;
  created_at: string;
}

export type TargetTool = 'chatgpt' | 'claude' | 'cursor' | 'generic';

// --- V2 Memory Types ---

export interface MemoryItem {
  id: string;
  user_id: string;
  type: string;
  content: string;
  source: string | null;
  confidence: number;
  importance: number;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ContextBuildResponse {
  target_tool: string;
  content: string;
  format: string;
}

// --- V2 Git for Memory Types ---

export interface Repo {
  id: string;
  repo_slug: string | null;
  name: string;
  description: string;
  user_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Artifact {
  id: string;
  type: string;
  label: string;
  content: string;
}

export interface Commit {
  id: string;
  repo_id: string;
  commit_hash: string;
  parent_commit_id: string | null;
  branch_name: string;
  author_agent: string | null;
  author_type: string;
  message: string;
  summary: string;
  objective: string;
  decisions: string[];
  assumptions: string[];
  tasks: string[];
  open_questions: string[];
  entities: string[];
  artifacts: Artifact[];
  context_blob: Record<string, unknown>;
  raw_source_text: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}
/** Delta between a commit and its parent, used for the diff view on CommitDetailPage */
export interface CommitDelta {
  current: Commit;
  parent: Commit | null;
}

// ── V4 Chat Types ─────────────────────────────────────────────────────────────

export interface ChatSession {
  id: string;
  repo_id: string;
  title: string;
  active_provider: string;
  active_model: string;
  seeded_commit_id: string | null;
  forked_from_checkpoint_id: string | null;
  branch_name: string;
  created_at: string;
  updated_at: string;
}

export interface TurnEvent {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  provider: string;
  model: string;
  sequence_number: number;
  created_at: string;
}

export interface SendMessageResponse {
  reply: string;
  session_id: string;
  turn_count: number;
  provider: string;
  model: string;
}

export interface HeadState {
  repo_id: string;
  commit_hash: string | null;
  commit_id: string | null;
  summary: string | null;
  objective: string | null;
  latest_session_id: string | null;
  latest_session_title: string | null;
}

export interface ProviderStatus {
  enabled?: boolean;
  has_key?: boolean;
  missing_package?: boolean;
  default_model?: string;
  provider?: string;
  model?: string;
}

export type ProviderName = 'openai' | 'anthropic' | 'openrouter';

// ── V5 Lineage Types ──────────────────────────────────────────────────────────

export interface ForkSessionResponse {
  session_id: string;
  branch_name: string;
  forked_from_checkpoint_id: string;
  history_base_seq: number;
}

export interface CheckpointNode {
  id: string;
  commit_hash: string;
  message: string;
  branch_name: string;
  parent_checkpoint_id: string | null;
  created_at: string;
  summary: string;
  objective: string;
  author_agent: string | null;
  note_count: number;
  note_kinds: string[];
}

export interface SessionNode {
  id: string;
  title: string;
  branch_name: string;
  forked_from_checkpoint_id: string | null;
  seeded_commit_id: string | null;
  branch_disposition: string;
  created_at: string;
}

export interface ActiveClaimSummary {
  id: string;
  agent: string;
  branch_name: string;
  scope: string;
  intent_type: string;
  claimed_at: string;
  expires_at: string;
  base_commit_hash: string | null;
}

export interface FreshnessInfo {
  changed: boolean;
  since_commit_hash: string;
  current_head_hash: string;
  new_checkpoints_count: number;
  new_checkpoints: {
    commit_hash: string;
    author_agent: string | null;
    message: string;
    created_at: string;
  }[];
}

export interface SpaceStateResponse {
  space: { id: string; name: string; description: string | null };
  head: any;
  commit: any;
  active_branches: any[];
  active_claims: ActiveClaimSummary[];
  divergence: any;
  freshness: FreshnessInfo | null;
}

export interface LineageResponse {
  space_id: string;
  checkpoints: CheckpointNode[];
  sessions: SessionNode[];
}

export interface CheckpointDetail {
  id: string;
  commit_hash: string;
  message: string;
  branch_name: string;
  summary: string;
  objective: string;
  decisions: string[];
  assumptions: string[];
  tasks: string[];
  open_questions: string[];
  artifacts: Artifact[];
}

export interface CheckpointDiff {
  summary_a: string;
  summary_b: string;
  objective_a: string;
  objective_b: string;
  decisions_only_a: string[];
  decisions_only_b: string[];
  decisions_shared: string[];
  assumptions_only_a: string[];
  assumptions_only_b: string[];
  assumptions_shared: string[];
  tasks_only_a: string[];
  tasks_only_b: string[];
  tasks_shared: string[];
}

export interface CompareResponse {
  checkpoint_a: CheckpointDetail;
  checkpoint_b: CheckpointDetail;
  diff: CheckpointDiff;
}

// ── Checkpoint Review Types ──────────────────────────────────────────────────

export interface ReviewIssue {
  type: 'contradiction' | 'hidden_assumption' | 'resolved_question' | 'unused_entity';
  description: string;
}

export interface CheckpointReviewResponse {
  checkpoint_id: string;
  issues: ReviewIssue[];
  suggestions: string[];
}
