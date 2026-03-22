import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  createChatCommit,
  createChatSessionGeneric,
  getChatSessionGeneric,
  getRepo,
  getRepos,
  createRepo,
  getRepoCommits,
  getCommit,
  getSessionTurnsGeneric,
  getSpaceHead,
  sendChatMessage,
  attachSession,
  draftCheckpoint,
  getRecentSessionsGeneric,
  getProviderStatus,
  generateThreadTitle,
  forkSession,
  compareCheckpoints,
  getSessionCheckpoints,
} from '../api/client';
import type { ChatSession, Commit, CompareResponse, HeadState, TurnEvent, Repo, ProviderStatus } from '../types';
import {
  Check,
  Copy,
  GitBranch,
  GitCommit,
  Loader2,
  MessageSquare,
  Send,
  Settings2,
  Terminal,
  Zap,
  FolderOpen,
  Plus,
  FolderInput,
} from 'lucide-react';

// ── Provider / model config ───────────────────────────────────────────────────

const PROVIDERS = [
  { id: 'openrouter', label: 'OpenRouter' },
  { id: 'openai',    label: 'OpenAI' },
  { id: 'anthropic', label: 'Anthropic' },
] as const;

type ProviderId = 'openrouter' | 'openai' | 'anthropic';

const MODELS: Record<ProviderId, { id: string, label: string }[]> = {
  openrouter: [
    { id: 'anthropic/claude-3.5-sonnet', label: 'Claude 3.5 Sonnet' },
    { id: 'meta-llama/llama-3-8b-instruct', label: 'Llama 3 8B' },
    { id: 'google/gemini-flash-1.5', label: 'Gemini 1.5 Flash' }
  ],
  openai: [
    { id: 'gpt-4o', label: 'GPT-4o' },
    { id: 'gpt-4o-mini', label: 'GPT-4o Mini' }
  ],
  anthropic: [
    { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
    { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' }
  ]
};



// ── Sub-components ────────────────────────────────────────────────────────────

/**
 * Light markdown renderer — handles the most common LLM output artifacts
 * without requiring a full markdown library.
 * Supports: ### headings, **bold**, `inline code`, ``` code blocks, bullet lists
 */
function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n');
  const nodes: React.ReactNode[] = [];
  let i = 0;

  const renderInline = (line: string, key: string | number): React.ReactNode => {
    // Split on **bold** and `code` patterns
    const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return (
      <span key={key}>
        {parts.map((part, j) => {
          if (part.startsWith('**') && part.endsWith('**')) {
            return <strong key={j} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
          }
          if (part.startsWith('`') && part.endsWith('`')) {
            return <code key={j} className="bg-zinc-800 text-emerald-300 px-1 py-0.5 rounded text-[12px] font-mono">{part.slice(1, -1)}</code>;
          }
          return part;
        })}
      </span>
    );
  };

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.trim().startsWith('```')) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      nodes.push(
        <pre key={i} className="bg-zinc-800 rounded-lg px-3 py-2 my-2 text-[12px] font-mono text-emerald-300 overflow-x-auto whitespace-pre-wrap">
          {codeLines.join('\n')}
        </pre>
      );
      i++;
      continue;
    }

    // Headings
    if (line.startsWith('### ')) {
      nodes.push(<p key={i} className="font-semibold text-white text-sm mt-3 mb-1">{line.slice(4)}</p>);
    } else if (line.startsWith('## ')) {
      nodes.push(<p key={i} className="font-semibold text-white text-sm mt-3 mb-1">{line.slice(3)}</p>);
    } else if (line.startsWith('# ')) {
      nodes.push(<p key={i} className="font-semibold text-white text-sm mt-3 mb-1">{line.slice(2)}</p>);
    // Bullet list
    } else if (line.match(/^[-*•]\s/)) {
      nodes.push(
        <div key={i} className="flex gap-2 my-0.5">
          <span className="text-gray-500 flex-shrink-0 mt-0.5">·</span>
          <span>{renderInline(line.slice(2), `${i}-inline`)}</span>
        </div>
      );
    // Empty line → spacing
    } else if (line.trim() === '') {
      nodes.push(<div key={i} className="h-2" />);
    // Normal line
    } else {
      nodes.push(<p key={i} className="my-0.5">{renderInline(line, `${i}-inline`)}</p>);
    }
    i++;
  }

  return nodes;
}

function MessageBubble({ turn }: { turn: TurnEvent }) {
  const [copied, setCopied] = useState(false);
  const isUser = turn.role === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(turn.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4 group`}>
      <div
        className={`relative max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-white text-black rounded-br-sm'
            : 'border border-gray-800 bg-zinc-900 text-gray-200 rounded-bl-sm'
        }`}
      >
        {isUser
          ? turn.content
          : <div className="space-y-0">{renderMarkdown(turn.content)}</div>
        }

        {!isUser && (
          <button
            onClick={handleCopy}
            className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-gray-800"
          >
            {copied
              ? <Check className="w-3 h-3 text-green-400" />
              : <Copy className="w-3 h-3 text-gray-500" />}
          </button>
        )}

        {!isUser && turn.model && (
          <div className="mt-2 flex items-center gap-1 text-[10px] text-gray-600">
            <span className="font-mono">{turn.model}</span>
            {turn.provider && <span>· {turn.provider}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="border border-gray-800 bg-zinc-900 rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
        <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  );
}

interface CommitModalProps {
  repoId: string;
  sessionId: string;
  onClose: () => void;
  onCommitted: (commit: Commit) => void;
  providerStatus: Record<string, ProviderStatus> | null;
  mountedCheckpointId?: string | null;
  mountedAtSeq?: number | null;
}

function CommitModal({ repoId, sessionId, onClose, onCommitted, providerStatus, mountedCheckpointId, mountedAtSeq }: CommitModalProps) {
  const [msg, setMsg]         = useState('');
  const [summary, setSummary] = useState('');
  const [obj, setObj]         = useState('');
  const [tasks, setTasks]     = useState('');
  const [decisions, setDecs]  = useState('');
  const [openQuestions, setOpenQuestions] = useState('');
  const [entities, setEntities] = useState('');
  const [loading, setLoading] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [err, setErr]         = useState<string | null>(null);

  const bgConfig = providerStatus?.['background_intelligence'];
  const bgProviderId = bgConfig?.provider;
  const isBgValid = bgProviderId ? providerStatus?.[bgProviderId]?.has_key : false;
  const bgTooltip = isBgValid ? "Draft with AI" : "Background Provider not configured in Settings";

  const parseLines = (text: string) => text.split('\n').map(l => l.trim()).filter(Boolean);

  const handleDraftWithAI = async () => {
    try {
      setDrafting(true);
      setErr(null);
      const draft = await draftCheckpoint({
        session_id: sessionId,
        mounted_checkpoint_id: mountedCheckpointId ?? null,
        history_base_seq: mountedCheckpointId !== null ? (mountedAtSeq ?? null) : null,
      });

      // Replace all fields — no merge, no accumulation
      setMsg(draft.title || '');
      setObj(draft.objective || '');
      setSummary(draft.summary || '');
      setTasks((draft.tasks ?? []).join('\n'));
      setDecs((draft.decisions ?? []).join('\n'));
      setOpenQuestions((draft.open_questions ?? []).join('\n'));
      setEntities((draft.entities ?? []).join('\n'));
    } catch (e: any) {
      setErr('Draft failed: ' + e.message);
    } finally {
      setDrafting(false);
    }
  };

  const handleSubmit = async () => {
    if (!msg.trim()) { setErr('Checkpoint message is required'); return; }
    try {
      setLoading(true);
      setErr(null);
      const commit = await createChatCommit({
        repo_id: repoId,
        session_id: sessionId,
        message: msg.trim(),
        summary: summary.trim(),
        objective: obj.trim(),
        tasks: parseLines(tasks),
        decisions: parseLines(decisions),
        open_questions: parseLines(openQuestions),
        entities: parseLines(entities),
      });
      onCommitted(commit);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-2xl bg-zinc-950 border border-gray-800 rounded-xl shadow-2xl overflow-hidden my-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <GitCommit className="w-4 h-4 text-gray-400" /> Create Checkpoint
          </h2>
          <div className="flex items-center gap-3">
            <button
              onClick={handleDraftWithAI}
              disabled={!isBgValid || drafting || loading}
              title={bgTooltip}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-purple-200 bg-purple-900/30 hover:bg-purple-900/50 border border-purple-500/30 rounded-md transition-colors disabled:opacity-50 disabled:grayscale"
            >
              {drafting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
              {drafting ? "Drafting…" : "Draft with AI"}
            </button>
            <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors text-sm">
              Cancel
            </button>
          </div>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {err && <p className="text-red-400 text-sm">{err}</p>}

          <div>
            <label className="text-xs uppercase tracking-wider text-gray-500 block mb-1.5">
              Message <span className="text-red-400">*</span>
            </label>
            <input
              className="w-full bg-zinc-900/50 border border-gray-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-gray-500 transition-colors"
              placeholder="e.g. Added user auth, resolved database choice"
              value={msg}
              onChange={e => setMsg(e.target.value)}
            />
          </div>

          <div>
            <label className="text-xs uppercase tracking-wider text-gray-500 block mb-1.5">
              Objective
            </label>
            <input
              className="w-full bg-zinc-900/50 border border-gray-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-gray-500 transition-colors"
              placeholder="What are we working toward?"
              value={obj}
              onChange={e => setObj(e.target.value)}
            />
          </div>

          <div>
            <label className="text-xs uppercase tracking-wider text-gray-500 block mb-1.5">
              Summary
            </label>
            <textarea
              className="w-full bg-zinc-900/50 border border-gray-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-gray-500 transition-colors resize-none"
              rows={2}
              placeholder="Brief narrative of what was figured out…"
              value={summary}
              onChange={e => setSummary(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs uppercase tracking-wider text-gray-500 block mb-1.5">
                Tasks (one per line)
              </label>
              <textarea
                className="w-full bg-zinc-900/50 border border-gray-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-gray-500 transition-colors resize-none font-mono"
                rows={3}
                placeholder={"Set up database\nWrite tests"}
                value={tasks}
                onChange={e => setTasks(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-gray-500 block mb-1.5">
                Decisions (one per line)
              </label>
              <textarea
                className="w-full bg-zinc-900/50 border border-gray-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-gray-500 transition-colors resize-none font-mono"
                rows={3}
                placeholder={"Use Postgres\nNo auth for now"}
                value={decisions}
                onChange={e => setDecs(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-gray-500 block mb-1.5">
                Open Questions (one per line)
              </label>
              <textarea
                className="w-full bg-zinc-900/50 border border-gray-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-gray-500 transition-colors resize-none font-mono"
                rows={3}
                placeholder={"How to handle caching?\nWhich OAuth provider?"}
                value={openQuestions}
                onChange={e => setOpenQuestions(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider text-gray-500 block mb-1.5">
                Entities (one per line)
              </label>
              <textarea
                className="w-full bg-zinc-900/50 border border-gray-800 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-gray-500 transition-colors resize-none font-mono"
                rows={3}
                placeholder={"Redis\nReact\nPostgreSQL"}
                value={entities}
                onChange={e => setEntities(e.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-gray-800">
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="w-full bg-white text-black hover:bg-gray-200 rounded-lg py-2.5 flex items-center justify-center gap-2 font-medium transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitCommit className="w-4 h-4" />}
            {loading ? 'Creating Checkpoint…' : 'Create Checkpoint'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── CheckpointDetailPanel ─────────────────────────────────────────────────────

function CheckpointDetailPanel({ commit, onClose }: { commit: Commit; onClose: () => void }) {
  const fmt = (d: string) => new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  const rows = (items: string[], label: string) =>
    items.length > 0 ? (
      <div>
        <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{label}</p>
        <ul className="space-y-0.5">
          {items.map((item, i) => (
            <li key={i} className="text-xs text-gray-300 flex gap-2">
              <span className="text-gray-600 flex-shrink-0">–</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>
    ) : null;

  return (
    <div className="border-t border-gray-800 pt-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-white">{commit.message}</h3>
        <button onClick={onClose} className="text-gray-600 hover:text-gray-300 text-xs">↑ close</button>
      </div>
      <div className="flex items-center gap-3 text-[10px] text-gray-600">
        <code className="text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">{commit.commit_hash.slice(0, 7)}</code>
        <span>{fmt(commit.created_at)}</span>
      </div>
      {commit.objective && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Objective</p>
          <p className="text-xs text-gray-300">{commit.objective}</p>
        </div>
      )}
      {commit.summary && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Summary</p>
          <p className="text-xs text-gray-400 leading-relaxed">{commit.summary}</p>
        </div>
      )}
      {rows(commit.tasks ?? [], 'Tasks')}
      {rows(commit.decisions ?? [], 'Decisions')}
      {rows(commit.open_questions ?? [], 'Open Questions')}
      {rows(commit.entities ?? [], 'Entities')}
    </div>
  );
}

// ── ForkModal ─────────────────────────────────────────────────────────────────

function ForkModal({
  spaceId,
  checkpoint,
  onClose,
  onForked,
}: {
  spaceId: string;
  checkpoint: Commit;
  onClose: () => void;
  onForked: (sessionId: string) => void;
}) {
  const [branchName, setBranchName] = useState(
    `branch-${new Date().toISOString().slice(0, 10)}`,
  );
  const [forking, setForking] = useState(false);
  const [err, setErr] = useState('');

  const handleFork = async () => {
    try {
      setForking(true);
      setErr('');
      const resp = await forkSession({
        space_id: spaceId,
        checkpoint_id: checkpoint.id,
        branch_name: branchName.trim() || undefined,
      });
      onForked(resp.session_id);
    } catch (e: any) {
      setErr(e.message || 'Fork failed');
      setForking(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="w-full max-w-sm rounded-xl border p-6 space-y-4"
        style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-purple-400" />
            <h2 className="text-sm font-semibold text-white">Fork from checkpoint</h2>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-sm">✕</button>
        </div>

        <div className="text-[11px] text-gray-500 space-y-0.5">
          <p>Branching from:</p>
          <div className="flex items-center gap-2">
            <code className="text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">
              {checkpoint.commit_hash.slice(0, 7)}
            </code>
            <span className="text-gray-400 truncate">{checkpoint.message}</span>
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] uppercase tracking-wider text-gray-500">Branch name</label>
          <input
            type="text"
            value={branchName}
            onChange={e => setBranchName(e.target.value)}
            className="w-full text-sm rounded-lg border px-3 py-2 bg-transparent text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-purple-500"
            style={{ borderColor: 'var(--color-border)' }}
            placeholder="branch-2026-03-21"
          />
        </div>

        {err && <p className="text-xs text-red-400">{err}</p>}

        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onClose}
            className="text-xs px-3 py-1.5 rounded-md border text-gray-400 hover:text-white transition-colors"
            style={{ borderColor: 'var(--color-border)' }}
          >
            Cancel
          </button>
          <button
            onClick={handleFork}
            disabled={forking}
            className="text-xs px-4 py-1.5 rounded-md font-medium transition-colors flex items-center gap-1.5 disabled:opacity-50"
            style={{ background: '#7c3aed', color: 'white' }}
          >
            {forking ? <Loader2 className="w-3 h-3 animate-spin" /> : <GitBranch className="w-3 h-3" />}
            {forking ? 'Creating…' : 'Create branch'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── MemorySpacePanel ──────────────────────────────────────────────────────────

function MemorySpacePanel({
  repoId,
  currentSession,
  spaceSessions,
  forkSourceCommit,
  mountedCheckpointId,
  refreshKey,
  onMount,
  onFork,
  onClose,
}: {
  repoId: string;
  currentSession: ChatSession | null;
  spaceSessions: ChatSession[];
  forkSourceCommit: Commit | null;
  mountedCheckpointId: string | null;
  /** Increment to force the checkpoint list to reload (e.g. after creating a new checkpoint). */
  refreshKey: number;
  onMount: (id: string | null) => void;
  onFork: (checkpoint: Commit) => void;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [checkpoints, setCheckpoints] = useState<Commit[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedCommit, setExpandedCommit] = useState<Commit | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Compare: up to 2 checkpoint IDs selected; when both set, show compare panel
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [showSessions, setShowSessions] = useState(false);

  // Load the reachable checkpoint set for the current session.
  // Uses getSessionCheckpoints (branch-aware) when a session is active;
  // falls back to all-repo commits (main only) when no session is loaded.
  // Re-fires when the session changes or refreshKey increments (post-commit).
  useEffect(() => {
    setLoading(true);
    const loader = currentSession?.id
      ? getSessionCheckpoints(currentSession.id)
      : getRepoCommits(repoId, 'main');
    loader
      .then(c => setCheckpoints(c))
      .catch(() => setCheckpoints([]))
      .finally(() => setLoading(false));
  }, [currentSession?.id, repoId, refreshKey]);

  const toggleDetail = async (id: string) => {
    if (expandedId === id) { setExpandedId(null); setExpandedCommit(null); return; }
    setExpandedId(id);
    setDetailLoading(true);
    try {
      setExpandedCommit(await getCommit(id));
    } catch { setExpandedCommit(null); }
    finally { setDetailLoading(false); }
  };

  const toggleCompareSelect = (id: string) => {
    setCompareIds(prev => {
      if (prev.includes(id)) return prev.filter(x => x !== id);
      if (prev.length >= 2) return [prev[1], id];
      return [...prev, id];
    });
    setCompareResult(null);
  };

  const handleCompare = async () => {
    if (compareIds.length !== 2) return;
    setCompareLoading(true);
    try {
      setCompareResult(await compareCheckpoints(compareIds[0], compareIds[1]));
    } catch { /* noop */ }
    finally { setCompareLoading(false); }
  };

  const fmt = (d: string) =>
    new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

  const isFork = currentSession?.branch_name && currentSession.branch_name !== 'main';

  return (
    <div className="absolute inset-y-0 right-0 w-80 bg-zinc-950 border-l border-gray-800 flex flex-col z-30 shadow-2xl">

      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-white">Space History</h2>
        <div className="flex items-center gap-3">
          {compareIds.length === 2 && !compareResult && (
            <button
              onClick={handleCompare}
              disabled={compareLoading}
              className="text-[11px] text-blue-400 hover:text-blue-300 border border-blue-500/30 px-2 py-0.5 rounded transition-colors flex items-center gap-1"
            >
              {compareLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              Compare
            </button>
          )}
          {compareIds.length > 0 && (
            <button
              onClick={() => { setCompareIds([]); setCompareResult(null); }}
              className="text-[10px] text-gray-600 hover:text-gray-400 transition-colors"
            >
              Clear
            </button>
          )}
          <a
            href={`/spaces/${repoId}/lineage?session=${currentSession?.id ?? ''}`}
            className="text-[11px] text-gray-500 hover:text-purple-400 transition-colors flex items-center gap-1"
          >
            <GitBranch className="w-3 h-3" />
            Branch tree
          </a>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">✕</button>
        </div>
      </div>

      {/* Current context context strip */}
      <div className="px-4 py-2 border-b border-gray-800 space-y-1">
        {mountedCheckpointId ? (
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-amber-500 flex items-center gap-1">
              <span className="text-[9px]">⊕</span>
              MOUNTED · <code className="text-amber-400">{mountedCheckpointId.slice(0, 7)}</code>
              <span className="text-gray-600 ml-0.5">(temporary override)</span>
            </span>
            <button
              onClick={() => onMount(null)}
              className="text-[10px] text-gray-600 hover:text-red-400 transition-colors ml-2 flex-shrink-0"
            >
              Unmount
            </button>
          </div>
        ) : isFork ? (
          <div className="flex items-center gap-1.5 text-[10px]">
            <GitBranch className="w-3 h-3 text-purple-400 flex-shrink-0" />
            <span className="text-purple-400">{currentSession!.branch_name}</span>
            {forkSourceCommit && (
              <span className="text-gray-600">
                · forked from <code className="text-blue-400">{forkSourceCommit.commit_hash.slice(0, 7)}</code>
              </span>
            )}
          </div>
        ) : (
          <span className="text-[10px] text-gray-700">branch: main</span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">

        {/* Checkpoint list */}
        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-gray-500" /></div>
        ) : checkpoints.length === 0 ? (
          <div className="px-4 py-6 text-sm text-gray-600 text-center">No checkpoints yet.<br />Create one from the thread header.</div>
        ) : (
          <>
            {compareIds.length > 0 && (
              <div className="px-4 py-1.5 bg-blue-900/10 border-b border-blue-500/20">
                <span className="text-[10px] text-blue-400">
                  {compareIds.length === 1 ? 'Select one more to compare' : '2 selected — click Compare'}
                </span>
              </div>
            )}
            <div className="divide-y divide-gray-900">
              {checkpoints.map(c => {
                const isMounted = c.id === mountedCheckpointId;
                const isExpanded = expandedId === c.id;
                const isSelectedForCompare = compareIds.includes(c.id);
                return (
                  <div key={c.id} className={`px-4 py-3 ${isMounted ? 'bg-amber-900/5 border-l-2 border-amber-500/40' : ''}`}>
                    <div className="flex items-start gap-2">
                      {/* Compare checkbox */}
                      <button
                        onClick={() => toggleCompareSelect(c.id)}
                        title="Select for compare"
                        className={`w-4 h-4 rounded border flex-shrink-0 mt-0.5 transition-colors flex items-center justify-center ${
                          isSelectedForCompare
                            ? 'border-blue-500 bg-blue-500/20'
                            : 'border-gray-800 hover:border-gray-600'
                        }`}
                      >
                        {isSelectedForCompare && <span className="text-blue-400 text-[8px]">✓</span>}
                      </button>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <code className="text-[10px] font-mono text-blue-400">{c.commit_hash.slice(0, 7)}</code>
                          {isMounted && (
                            <span className="text-[9px] uppercase tracking-wider text-amber-400 bg-amber-500/15 px-1.5 py-0.5 rounded">
                              Mounted
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-300 truncate font-medium">{c.message}</p>
                        {c.summary && (
                          <p className="text-[11px] text-gray-600 mt-0.5 line-clamp-2">{c.summary}</p>
                        )}
                        <p className="text-[10px] text-gray-700 mt-1">{fmt(c.created_at)}</p>
                      </div>

                      <div className="flex flex-col gap-1.5 flex-shrink-0">
                        <button
                          onClick={() => onMount(isMounted ? null : c.id)}
                          title={isMounted ? 'Remove temporary context override' : 'Temporarily rebase context onto this checkpoint'}
                          className={`text-xs px-3 py-1.5 rounded-md border font-medium transition-colors ${
                            isMounted
                              ? 'border-amber-500/50 text-amber-300 bg-amber-900/20 hover:bg-red-900/20 hover:text-red-300 hover:border-red-500/40'
                              : 'border-gray-700 text-gray-400 hover:bg-amber-900/10 hover:text-amber-300 hover:border-amber-500/40'
                          }`}
                        >
                          {isMounted ? 'Unmount' : 'Mount'}
                        </button>
                        <button
                          onClick={() => toggleDetail(c.id)}
                          className="text-xs px-3 py-1.5 rounded-md border border-gray-800 text-gray-500 hover:text-gray-300 hover:bg-zinc-800 transition-colors"
                        >
                          {isExpanded ? 'Hide' : 'Details'}
                        </button>
                        <button
                          onClick={() => onFork(c)}
                          title="Create a new independent session branched from this checkpoint"
                          className="text-xs px-3 py-1.5 rounded-md border border-gray-800 text-gray-500 hover:text-purple-300 hover:border-purple-500/40 hover:bg-purple-900/20 transition-colors flex items-center gap-1"
                        >
                          <GitBranch className="w-3 h-3" />
                          Fork
                        </button>
                      </div>
                    </div>

                    {isExpanded && (
                      detailLoading
                        ? <div className="mt-2 flex justify-center"><Loader2 className="w-4 h-4 animate-spin text-gray-500" /></div>
                        : expandedCommit && (
                          <CheckpointDetailPanel
                            commit={expandedCommit}
                            onClose={() => { setExpandedId(null); setExpandedCommit(null); }}
                          />
                        )
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Inline compare result */}
        {compareResult && (
          <div className="border-t border-gray-800 px-4 py-3 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[10px] uppercase tracking-wider text-gray-500">Compare</p>
              <button onClick={() => { setCompareResult(null); setCompareIds([]); }} className="text-[10px] text-gray-600 hover:text-gray-400">Clear</button>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[10px]">
              <div className="text-blue-400 font-mono">{compareResult.checkpoint_a.commit_hash.slice(0, 7)}</div>
              <div className="text-green-400 font-mono">{compareResult.checkpoint_b.commit_hash.slice(0, 7)}</div>
            </div>
            {[
              { label: 'Decisions', onlyA: compareResult.diff.decisions_only_a, onlyB: compareResult.diff.decisions_only_b, shared: compareResult.diff.decisions_shared },
              { label: 'Tasks', onlyA: compareResult.diff.tasks_only_a, onlyB: compareResult.diff.tasks_only_b, shared: compareResult.diff.tasks_shared },
            ].map(({ label, onlyA, onlyB, shared }) => (onlyA.length + onlyB.length + shared.length) > 0 && (
              <div key={label}>
                <p className="text-[9px] uppercase tracking-wider text-gray-600 mb-1">{label}</p>
                {onlyA.map((d, i) => <div key={i} className="text-[11px] text-blue-300 px-1.5 py-0.5 bg-blue-900/10 rounded mb-0.5 truncate">{d}</div>)}
                {shared.map((d, i) => <div key={i} className="text-[11px] text-gray-500 px-1.5 py-0.5 bg-zinc-800 rounded mb-0.5 truncate">{d}</div>)}
                {onlyB.map((d, i) => <div key={i} className="text-[11px] text-green-300 px-1.5 py-0.5 bg-green-900/10 rounded mb-0.5 truncate">{d}</div>)}
              </div>
            ))}
          </div>
        )}

        {/* Sessions in this space */}
        {spaceSessions.length > 0 && (
          <div className="border-t border-gray-800">
            <button
              onClick={() => setShowSessions(s => !s)}
              className="w-full px-4 py-2.5 flex items-center justify-between text-[10px] uppercase tracking-wider text-gray-600 hover:text-gray-400 transition-colors"
            >
              <span>Sessions in this space ({spaceSessions.length})</span>
              <span>{showSessions ? '▲' : '▼'}</span>
            </button>
            {showSessions && (
              <div className="divide-y divide-gray-900">
                {spaceSessions.map(s => {
                  const isCurrentSession = s.id === currentSession?.id;
                  const isBranch = s.branch_name && s.branch_name !== 'main';
                  return (
                    <button
                      key={s.id}
                      onClick={() => navigate(`/sessions/${s.id}`)}
                      className={`w-full px-4 py-2.5 text-left flex items-start gap-2 hover:bg-zinc-900 transition-colors ${isCurrentSession ? 'border-l-2 border-purple-500' : 'border-l-2 border-transparent'}`}
                    >
                      {isBranch
                        ? <GitBranch className="w-3 h-3 text-purple-400 flex-shrink-0 mt-0.5" />
                        : <MessageSquare className="w-3 h-3 text-gray-600 flex-shrink-0 mt-0.5" />}
                      <div className="min-w-0">
                        <div className="text-xs text-gray-300 truncate">{s.title || 'Untitled'}</div>
                        {isBranch && <div className="text-[9px] text-purple-500 truncate">{s.branch_name}</div>}
                        {isCurrentSession && <div className="text-[9px] text-gray-600">← you are here</div>}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

type MemoryScope = 'latest_1' | 'latest_3';

const SCOPE_LABELS: Record<MemoryScope, string> = {
  latest_1: 'Latest checkpoint only',
  latest_3: 'Latest 3 checkpoints',
};

function AttachModal({ sessionId, onClose, onAttached }: {
  sessionId: string;
  onClose: () => void;
  onAttached: (repo: Repo, scope: MemoryScope) => void;
}) {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [attaching, setAttaching] = useState(false);
  const [err, setErr] = useState('');
  const [newName, setNewName] = useState('');
  const [scope, setScope] = useState<MemoryScope>('latest_1');

  useEffect(() => {
    getRepos().then(setRepos).catch(() => setErr('Failed to load spaces')).finally(() => setLoading(false));
  }, []);

  const handleAttach = async (repoId: string) => {
    try {
      setAttaching(true);
      await attachSession(sessionId, repoId);
      const repo = repos.find(r => r.id === repoId);
      if (repo) onAttached(repo, scope);
    } catch (e: any) {
      setErr(e.message);
      setAttaching(false);
    }
  };

  const handleCreateAndAttach = async () => {
    if (!newName.trim()) return;
    try {
      setAttaching(true);
      const repo = await createRepo({ name: newName.trim(), description: 'Created from chat' });
      await attachSession(sessionId, repo.id);
      onAttached(repo, scope);
    } catch (e: any) {
      setErr(e.message);
      setAttaching(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-sm mx-4 bg-zinc-950 border border-gray-800 rounded-xl shadow-2xl overflow-hidden p-5">
        <h2 className="font-semibold text-white mb-4">Attach to Memory Space</h2>
        {err && <p className="text-red-400 text-sm mb-3">{err}</p>}

        {/* Memory Scope Selector */}
        <div className="mb-4">
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">Memory Scope</p>
          <div className="flex gap-2">
            {(Object.keys(SCOPE_LABELS) as MemoryScope[]).map(s => (
              <button
                key={s}
                onClick={() => setScope(s)}
                className={`flex-1 px-3 py-1.5 rounded-lg border text-xs transition-colors ${
                  scope === s
                    ? 'bg-purple-900/40 border-purple-500/50 text-purple-200 font-medium'
                    : 'border-gray-800 text-gray-500 hover:text-gray-300 hover:bg-zinc-900'
                }`}
              >
                {SCOPE_LABELS[s]}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-4"><Loader2 className="w-5 h-5 animate-spin text-gray-500" /></div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {repos.length === 0 ? <p className="text-sm text-gray-500">No spaces exist yet.</p> : repos.map(r => (
                <button
                  key={r.id}
                  onClick={() => handleAttach(r.id)}
                  disabled={attaching}
                  className="w-full flex items-center gap-2 text-left px-3 py-2 rounded border border-gray-800 hover:bg-zinc-900 transition-colors text-sm text-gray-300 disabled:opacity-50"
                >
                  <FolderOpen className="w-4 h-4 text-gray-500" />
                  {r.name}
                </button>
              ))}
            </div>
            <div className="pt-3 border-t border-gray-800">
              <p className="text-xs text-gray-500 mb-2">Or create new space</p>
              <div className="flex gap-2">
                <input
                  className="flex-1 bg-zinc-900 border border-gray-800 rounded-lg px-3 py-1.5 text-sm text-white outline-none focus:border-gray-500"
                  placeholder="New space name"
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                />
                <button
                  onClick={handleCreateAndAttach}
                  disabled={!newName.trim() || attaching}
                  className="px-3 py-1.5 bg-white text-black rounded-lg text-sm font-medium hover:bg-gray-200 disabled:opacity-50 transition-colors"
                >
                  Create
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main ChatWorkspacePage ────────────────────────────────────────────────────

export function ChatWorkspacePage() {
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();

  const [repos, setRepos]             = useState<Repo[]>([]);
  const [repo, setRepo]               = useState<Repo | null>(null);
  const [session, setSession]         = useState<ChatSession | null>(null);
  const [recentSessions, setRecentSessions] = useState<ChatSession[]>([]);
  const [turns, setTurns]             = useState<TurnEvent[]>([]);
  const [head, setHead]               = useState<HeadState | null>(null);
  const [composerText, setComposerText] = useState('');
  const [loading, setLoading]         = useState(true);
  const [sending, setSending]         = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [showCommitModal, setShowCommitModal] = useState(false);
  const [showAttachModal, setShowAttachModal] = useState(false);

  // Provider / model selection
  const [provider, setProvider] = useState<ProviderId>('openrouter');
  const [model, setModel]       = useState(MODELS.openrouter[0].id);
  const [useMock, setUseMock]   = useState(false);

  // Memory scope for attached space
  const [memoryScope, setMemoryScope] = useState<MemoryScope>('latest_1');

  // Explicit checkpoint mounting (temporary context override)
  const [mountedCheckpointId, setMountedCheckpointId] = useState<string | null>(null);
  // Sequence number of the last turn that existed when the user clicked "Mount".
  // Only turns with sequence_number > mountedAtSeq are sent as history, preventing
  // pre-mount conversation state from leaking into the mounted commit's context.
  const [mountedAtSeq, setMountedAtSeq] = useState<number | null>(null);
  const [showHistoryPanel, setShowHistoryPanel] = useState(false);
  const [forkTarget, setForkTarget] = useState<Commit | null>(null);
  // The checkpoint this session was forked from (permanent identity for forked sessions)
  const [forkSourceCommit, setForkSourceCommit] = useState<Commit | null>(null);
  // Increment after a checkpoint is created so MemorySpacePanel re-fetches its list
  const [checkpointRefreshKey, setCheckpointRefreshKey] = useState(0);

  // Checkpoint recommendation logic
  const [recommendCheckpoint, setRecommendCheckpoint] = useState(false);
  const [turnsSinceCheckpoint, setTurnsSinceCheckpoint] = useState(0);

  const [providerStatus, setProviderStatus] = useState<Record<string, ProviderStatus> | null>(null);

  const threadEndRef = useRef<HTMLDivElement>(null);
  const autoTitleDone = useRef(false);

  const scrollToBottom = () => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  useEffect(() => {
    getRepos().then(setRepos).catch(console.error);
    getRecentSessionsGeneric().then(setRecentSessions).catch(console.error);
    getProviderStatus().then(setProviderStatus).catch(console.error);

    (async () => {
      try {
        setLoading(true);
        setError(null);

        let activeSession: ChatSession;
        
        if (routeSessionId) {
          // Load existing session
          activeSession = await getChatSessionGeneric(routeSessionId);
          setSession(activeSession);
          const t = await getSessionTurnsGeneric(routeSessionId);
          setTurns(t);

          if (activeSession.repo_id) {
            const [r, h] = await Promise.all([getRepo(activeSession.repo_id), getSpaceHead(activeSession.repo_id)]);
            setRepo(r);
            setHead(h);
          } else {
            setRepo(null);
            setHead(null);
          }

          // Load fork source commit so the header can show which checkpoint this session branched from.
          // Also open the history panel once so the user can immediately see their fork-local
          // reachable checkpoints. This fires exactly once per session-load (it is inside the
          // useEffect([routeSessionId]) bootstrap); the user closing the panel afterwards keeps
          // it closed — the panel state is not re-set unless the route session changes again.
          if (activeSession.forked_from_checkpoint_id) {
            getCommit(activeSession.forked_from_checkpoint_id).then(setForkSourceCommit).catch(() => {});
            setShowHistoryPanel(true);
          }
        } else {
          // Create new unattached session
          activeSession = await createChatSessionGeneric({
            title: `Session ${new Date().toLocaleTimeString()}`,
            provider,
            model,
            seed_from: 'none',
          });
          setSession(activeSession);
          setTurns([]);
          setRepo(null);
          setHead(null);
          navigate(`/sessions/${activeSession.id}`, { replace: true });
        }
      } catch (e: any) {
        setError(e.message || 'Failed to open workspace');
      } finally {
        setLoading(false);
      }
    })();
  }, [routeSessionId]);

  // Reset per-session UI state whenever the route session changes.
  // ChatWorkspacePage is NOT remounted on route changes — React Router just
  // re-renders it with new params. Without this reset, stale state from session A
  // (mounted checkpoint, fork source, open panel) would persist in session B.
  // showHistoryPanel is reset to false here; the bootstrap below re-opens it
  // intentionally for forked sessions as part of that session's load sequence.
  useEffect(() => {
    setMountedCheckpointId(null);
    setMountedAtSeq(null);
    setForkSourceCommit(null);
    setShowHistoryPanel(false);
  }, [routeSessionId]);

  useEffect(() => { scrollToBottom(); }, [turns, sending]);

  // Recommendation logic evaluation
  useEffect(() => {
    if (!session || turns.length === 0) return;
    
    // Calculate turns since last checkpoint
    // In a real app we'd track this via commit_id on TurnEvent, but we'll approximate 
    // simply by total turns for this Demo MVP, or resetting when checkpoint is made
    if (turnsSinceCheckpoint > 10) {
      setRecommendCheckpoint(true);
      return;
    }

    const lastUserTurn = turns.filter(t => t.role === 'user').pop();
    if (lastUserTurn) {
      const txt = lastUserTurn.content.toLowerCase();
      const keywords = ["finalize", "decision", "we should go with", "let's proceed with"];
      if (keywords.some(k => txt.includes(k))) {
        setRecommendCheckpoint(true);
        return;
      }
    }
  }, [turns, turnsSinceCheckpoint]);

  const handleModelChange = (newProvider: ProviderId, newModel: string) => {
    if (provider !== newProvider || model !== newModel) {
      setProvider(newProvider);
      setModel(newModel);
      // Switching models is a great time to suggest a checkpoint
      if (turns.length > 0) setRecommendCheckpoint(true);
    }
  };

  // ── Send message ───────────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    if (!composerText.trim() || !session) return;

    const effectiveModel = model.trim();
    if (!effectiveModel && !useMock) {
      setError('Enter a model name before sending');
      return;
    }

    const text = composerText.trim();
    setComposerText('');
    setError(null);

    const optimisticUser: TurnEvent = {
      id: `opt-${Date.now()}`,
      session_id: session.id,
      role: 'user',
      content: text,
      provider,
      model: effectiveModel,
      sequence_number: turns.length,
      created_at: new Date().toISOString(),
    };
    setTurns(prev => [...prev, optimisticUser]);
    setSending(true);

    try {
      const resp = await sendChatMessage({
        session_id: session.id,
        repo_id: repo?.id,
        provider,
        model: effectiveModel || 'mock',
        message: text,
        use_mock: useMock,
        memory_scope: memoryScope,
        mounted_checkpoint_id: mountedCheckpointId,
        history_base_seq: mountedCheckpointId !== null ? mountedAtSeq : null,
      });

      const fresh = await getSessionTurnsGeneric(session.id);
      setTurns(fresh);
      setTurnsSinceCheckpoint(prev => prev + 2); // user + assistant turn

      setSession(prev => prev ? {
        ...prev,
        active_provider: resp.provider,
        active_model: resp.model,
      } : prev);

      // Auto-title: trigger once after first assistant reply if background provider is available
      if (!autoTitleDone.current && fresh.length >= 2) {
        const bgConfig = providerStatus?.['background_intelligence'];
        const bgProviderId = bgConfig?.provider;
        const isBgValid = bgProviderId ? providerStatus?.[bgProviderId]?.has_key : false;
        if (isBgValid) {
          autoTitleDone.current = true;
          generateThreadTitle(session.id).then(updated => {
            setSession(prev => prev ? { ...prev, title: updated.title } : prev);
            setRecentSessions(prev => prev.map(s => s.id === updated.id ? { ...s, title: updated.title } : s));
          }).catch(() => { /* non-fatal */ });
        }
      }

    } catch (e: any) {
      setError(e.message || 'Failed to send message');
      setTurns(prev => prev.filter(t => t.id !== optimisticUser.id));
    } finally {
      setSending(false);
    }
  }, [composerText, session, repo, provider, model, useMock, turns.length]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleCommitted = (commit: Commit) => {
    setShowCommitModal(false);
    setRecommendCheckpoint(false);
    setTurnsSinceCheckpoint(0);
    setHead(prev => prev ? {
      ...prev,
      commit_hash: commit.commit_hash,
      commit_id: commit.id,
    } : prev);
    // Trigger MemorySpacePanel to reload its checkpoint list with the new commit
    setCheckpointRefreshKey(k => k + 1);
  };

  const handleAttached = async (newRepo: Repo, scope: MemoryScope) => {
    setShowAttachModal(false);
    setRepo(newRepo);
    setMemoryScope(scope);
    setMountedCheckpointId(null); // reset explicit mount when changing space
    setMountedAtSeq(null);
    const h = await getSpaceHead(newRepo.id);
    setHead(h);
    getRepos().then(setRepos);
  };

  if (loading) return (
    <div className="flex items-center justify-center h-screen bg-black text-gray-500 gap-3">
      <Loader2 className="animate-spin w-5 h-5" />
      <span className="text-sm">Opening workspace…</span>
    </div>
  );

  return (
    <>
      {showCommitModal && session && (
        <CommitModal
          repoId={repo?.id!}
          sessionId={session.id}
          onClose={() => setShowCommitModal(false)}
          onCommitted={handleCommitted}
          providerStatus={providerStatus}
          mountedCheckpointId={mountedCheckpointId}
          mountedAtSeq={mountedAtSeq}
        />
      )}

      {showAttachModal && session && (
        <AttachModal sessionId={session.id} onClose={() => setShowAttachModal(false)} onAttached={handleAttached} />
      )}

      <div className="flex h-screen overflow-hidden bg-black text-white">

        {/* ── Left Sidebar: Spaces ────────────────────────────────────── */}
        <aside className="w-56 flex-shrink-0 border-r border-gray-900 flex flex-col bg-zinc-950">
          <div className="p-4 border-b border-gray-900 flex items-center justify-between">
            <a href="/" className="flex items-center gap-2 no-underline">
              <span
                className="text-xl font-bold"
                style={{
                  background: 'linear-gradient(135deg, #8b5cf6, #a78bfa)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                स्मृति
              </span>
              <span className="text-sm font-semibold text-gray-300">Smriti</span>
            </a>
            <button
              onClick={() => navigate('/')}
              title="New Thread"
              className="p-1.5 rounded-md hover:bg-zinc-800 text-gray-400 transition-colors"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-4">
            {/* Recent Threads */}
            <div>
              <p className="text-[10px] uppercase tracking-widest text-gray-600 px-2 mb-2">Recent Threads</p>
              <div className="space-y-0.5">
                {recentSessions.slice(0, 12).map(s => {
                  const isActive = session?.id === s.id;
                  const isFork = s.branch_name && s.branch_name !== 'main';
                  return (
                    <button
                      key={s.id}
                      onClick={() => navigate(`/sessions/${s.id}`)}
                      title={s.title}
                      className={`w-full flex items-start gap-2 px-2 py-1.5 rounded-lg text-sm text-left transition-colors ${
                        isActive
                          ? 'bg-zinc-800 text-white border-l-2 border-purple-500'
                          : 'text-gray-400 hover:bg-zinc-800 hover:text-gray-300 border-l-2 border-transparent'
                      }`}
                    >
                      {isFork
                        ? <GitBranch className="w-3.5 h-3.5 flex-shrink-0 text-purple-400 mt-0.5" />
                        : <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />}
                      <div className="min-w-0 flex-1">
                        <div className="truncate">{s.title || 'Untitled Thread'}</div>
                        {isFork && (
                          <div className="text-[9px] text-purple-500 truncate mt-0.5">{s.branch_name}</div>
                        )}
                      </div>
                    </button>
                  );
                })}
                {recentSessions.length === 0 && (
                  <div className="px-2 py-1 text-xs text-gray-600 italic">No threads yet</div>
                )}
              </div>
            </div>

            {/* Memory Spaces */}
            <div>
              <p className="text-[10px] uppercase tracking-widest text-gray-600 px-2 mb-2">Memory Spaces</p>
              <div className="space-y-0.5">
                {repos.map(r => (
                  <button
                    key={r.id}
                    onClick={() => navigate(`/debug/repos/${r.id}`)}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm text-left transition-colors truncate ${
                      repo?.id === r.id ? 'bg-zinc-800 text-white' : 'text-gray-400 hover:bg-zinc-800 hover:text-gray-300'
                    }`}
                  >
                    <FolderOpen className="w-3.5 h-3.5 flex-shrink-0" />
                    <span className="truncate">{r.name}</span>
                  </button>
                ))}
                {repos.length === 0 && (
                  <div className="px-2 py-1 text-xs text-gray-600 italic">No spaces yet</div>
                )}
              </div>
            </div>
          </div>
          
          <div className="p-3 border-t border-gray-900">
             <button
                onClick={() => navigate('/debug')}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm text-gray-500 hover:bg-zinc-800 transition-colors text-left"
              >
                <Settings2 className="w-3.5 h-3.5" /> Legacy Views
              </button>
          </div>
        </aside>

        {/* ── Center: Chat ─────────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0 relative">

          {/* Thread header — two rows: identity row + state row */}
          {(() => {
            // Derive the current context mode from strict priority order.
            // MOUNTED overrides everything (user explicitly picked a checkpoint).
            // FORKED is the session's permanent identity (set at fork time).
            // HEAD means we're tracking the latest checkpoint on main.
            // FRESH means no space or no checkpoints yet.
            const contextMode: 'FRESH' | 'HEAD' | 'MOUNTED' | 'FORKED' =
              mountedCheckpointId
                ? 'MOUNTED'
                : session?.forked_from_checkpoint_id
                  ? 'FORKED'
                  : head?.commit_hash
                    ? 'HEAD'
                    : 'FRESH';

            const modeChip = {
              FRESH: {
                classes: 'text-gray-600 bg-zinc-900 border-gray-800',
                label: 'FRESH',
                title: 'No checkpoint — context starts from scratch each message',
              },
              HEAD: {
                classes: 'text-blue-400 bg-blue-500/10 border-blue-500/30 hover:bg-blue-500/15 cursor-pointer',
                label: `HEAD · ${head?.commit_hash?.slice(0, 7)}`,
                title: `Tracking latest checkpoint · ${SCOPE_LABELS[memoryScope]}`,
              },
              MOUNTED: {
                classes: 'text-amber-400 bg-amber-500/10 border-amber-500/30 hover:bg-amber-500/15 cursor-pointer',
                label: `MOUNTED · ${mountedCheckpointId?.slice(0, 7)}`,
                title: 'Temporary context override — only turns after mount are included. Unmount to return to HEAD.',
              },
              FORKED: {
                classes: 'text-purple-400 bg-purple-500/10 border-purple-500/30 hover:bg-purple-500/15 cursor-pointer',
                label: `FORKED · ${forkSourceCommit?.commit_hash?.slice(0, 7) ?? session?.forked_from_checkpoint_id?.slice(0, 7)}`,
                title: `Forked from checkpoint ${forkSourceCommit?.commit_hash?.slice(0, 7)} — click to open branch checkpoint history`,
              },
            }[contextMode];

            return (
          <div className="flex-shrink-0 border-b border-gray-900 bg-zinc-950/50">
            {/* Row 1: title + actions */}
            <div className="px-5 pt-3 pb-1 flex items-center justify-between">
              <span className="text-sm font-medium text-white truncate max-w-[240px]">
                {session?.title || 'New Thread'}
              </span>
              <div className="flex items-center gap-2 relative">
                <button
                  onClick={() => {
                    if (!repo) {
                      setShowAttachModal(true);
                    } else {
                      setShowCommitModal(true);
                    }
                  }}
                  data-testid="create-checkpoint"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded border text-xs transition-colors relative ${
                    recommendCheckpoint
                      ? 'border-purple-500/50 text-purple-200 bg-purple-500/10 hover:bg-purple-500/20'
                      : 'border-gray-700 hover:bg-zinc-800 text-gray-300'
                  }`}
                >
                  <GitCommit className="w-3.5 h-3.5" />
                  {repo ? 'Create Checkpoint' : 'Attach to Checkpoint'}
                  {recommendCheckpoint && (
                    <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-purple-500 border border-black animate-pulse" title="Checkpoint Recommended" />
                  )}
                </button>
              </div>
            </div>

            {/* Row 2: Space · Branch · Mode · Base checkpoint */}
            <div className="px-5 pb-2.5 flex items-center gap-2 flex-wrap">
              {/* Space chip */}
              {repo ? (
                <button
                  onClick={() => setShowAttachModal(true)}
                  title="Change Memory Space"
                  data-testid="attach-project"
                  className="flex items-center gap-1 px-2 py-0.5 rounded border border-gray-800 hover:bg-zinc-800 transition-colors text-[10px] text-gray-400 flex-shrink-0"
                >
                  <FolderOpen className="w-3 h-3 text-gray-500" />
                  <span>{repo.name}</span>
                </button>
              ) : (
                <button
                  onClick={() => setShowAttachModal(true)}
                  data-testid="attach-project"
                  className="flex items-center gap-1 px-2 py-0.5 rounded border border-gray-800 border-dashed hover:border-gray-600 transition-colors text-[10px] text-gray-600 flex-shrink-0"
                >
                  <FolderInput className="w-3 h-3" />
                  No Space
                </button>
              )}

              {/* Branch chip — only shown when not on main; clickable to open/close the checkpoint panel */}
              {session?.branch_name && session.branch_name !== 'main' && (
                <button
                  onClick={() => setShowHistoryPanel(p => !p)}
                  title="Open branch checkpoint history"
                  className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border border-purple-500/30 text-purple-400 bg-purple-900/10 hover:bg-purple-900/20 transition-colors flex-shrink-0"
                >
                  <GitBranch className="w-3 h-3" />
                  {session.branch_name}
                </button>
              )}

              {/* Mode chip — FRESH (static) / HEAD · MOUNTED · FORKED (all clickable, open panel) */}
              {contextMode !== 'FRESH' ? (
                <button
                  onClick={() => setShowHistoryPanel(p => !p)}
                  title={modeChip.title}
                  className={`flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border transition-colors flex-shrink-0 ${modeChip.classes}`}
                >
                  {contextMode === 'MOUNTED'
                    ? <span className="text-[9px]">⊕</span>
                    : contextMode === 'FORKED'
                      ? <GitBranch className="w-3 h-3" />
                      : <GitCommit className="w-3 h-3" />}
                  {modeChip.label}
                </button>
              ) : (
                <span
                  title={modeChip.title}
                  className={`flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border flex-shrink-0 ${modeChip.classes}`}
                >
                  <Zap className="w-3 h-3" />
                  {modeChip.label}
                </span>
              )}

              {/* Provider/model — far right of the row */}
              {session && (
                <span className="text-[10px] font-mono text-gray-700 ml-auto flex-shrink-0">
                  {session.active_provider}/{(session.active_model || '').split('/').pop()}
                </span>
              )}
            </div>
          </div>
          );
          })()}

          {/* Thread */}
          <div className="flex-1 overflow-y-auto min-h-0 px-5 py-6">
            {error && (
              <div className="mb-4 bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-4 py-2.5 rounded-lg">
                {error}
              </div>
            )}

            {turns.length === 0 && !sending && (
              <div className="flex flex-col items-center justify-center h-full pb-20 text-center space-y-3">
                <div className="w-12 h-12 rounded-xl border border-gray-800 bg-zinc-900 flex items-center justify-center">
                  <MessageSquare className="w-5 h-5 text-gray-600" />
                </div>
                <div>
                  <p className="text-gray-300 font-medium">
                    {session?.forked_from_checkpoint_id
                      ? 'Exploring alternate direction'
                      : head?.commit_hash
                        ? 'Continuing from latest checkpoint'
                        : 'Start a new conversation'}
                  </p>
                  <p className="text-gray-600 text-sm mt-1">
                    {session?.forked_from_checkpoint_id
                      ? `Forked from ${forkSourceCommit?.commit_hash?.slice(0, 7) ?? session.forked_from_checkpoint_id.slice(0, 7)} — start typing to explore this branch`
                      : head?.summary
                        ? `Last context: ${head.summary.slice(0, 80)}…`
                        : 'Type your first message below to begin'}
                  </p>
                </div>
              </div>
            )}

            {turns.map(t => <MessageBubble key={t.id} turn={t} />)}
            {sending && <TypingIndicator />}
            <div ref={threadEndRef} />
          </div>

          {/* Compose bar */}
          <div className="flex-shrink-0 px-5 py-4 border-t border-gray-900 bg-black">
            {/* Model / Provider row */}
            <div className="flex items-center gap-2 mb-3">
              {/* Provider tabs */}
              <div data-testid="provider-select" className="flex items-center border border-gray-800 rounded-lg overflow-hidden">
                {PROVIDERS.map(p => (
                  <button
                    key={p.id}
                    onClick={() => handleModelChange(p.id as ProviderId, MODELS[p.id as ProviderId][0].id)}
                    data-testid={`provider-tab-${p.id}`}
                    className={`px-3 py-1.5 text-xs transition-colors ${
                      provider === p.id
                        ? 'bg-white text-black font-medium'
                        : 'text-gray-500 hover:text-gray-300 hover:bg-zinc-900'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              {/* Model select */}
              <select
                data-testid="model-select"
                className="flex-1 max-w-[200px] bg-zinc-950 border border-gray-800 rounded-lg px-2 py-1.5 text-xs text-gray-300 outline-none focus:border-gray-600 transition-colors cursor-pointer appearance-none truncate"
                value={model}
                onChange={e => handleModelChange(provider, e.target.value)}
              >
                {MODELS[provider].map(m => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>

              {/* Demo Mode Toggle */}
              <button
                onClick={() => setUseMock(m => !m)}
                title="Use Deterministic Simulated Provider (No API key required)"
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors flex-shrink-0 ${
                  useMock
                    ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300 font-medium'
                    : 'border-gray-800 text-gray-500 hover:text-gray-400 bg-zinc-900/50 hover:bg-zinc-800'
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                {useMock ? 'Mock Mode Active' : 'Mock Mode'}
              </button>
            </div>

            {/* Active context indicator — matches header mode vocabulary */}
            {repo && (
              <div className="text-[10px] font-mono mb-1 flex items-center gap-1.5">
                {mountedCheckpointId ? (
                  <span className="text-amber-600">ctx: MOUNTED · {mountedCheckpointId.slice(0, 7)} (temporary override)</span>
                ) : session?.forked_from_checkpoint_id ? (
                  <span className="text-purple-600">
                    ctx: FORKED · {forkSourceCommit?.commit_hash?.slice(0, 7) ?? session.forked_from_checkpoint_id.slice(0, 7)}
                  </span>
                ) : head?.commit_hash ? (
                  <span className="text-gray-600">ctx: HEAD · {head.commit_hash.slice(0, 7)} · {memoryScope}</span>
                ) : (
                  <span className="text-gray-700">ctx: FRESH</span>
                )}
              </div>
            )}

            {/* Message input + send */}
            <div className="flex items-end gap-3">
              <textarea
                data-testid="chat-input"
                className="flex-1 bg-zinc-950 border border-gray-800 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-700 outline-none focus:border-gray-600 transition-colors resize-none min-h-[44px] max-h-36"
                placeholder="Message…"
                rows={1}
                value={composerText}
                onChange={e => setComposerText(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={sending}
              />
              <button
                onClick={handleSend}
                data-testid="send-action"
                disabled={sending || !composerText.trim()}
                className="flex-shrink-0 w-10 h-10 rounded-xl bg-white text-black flex items-center justify-center hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                {sending
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Send className="w-4 h-4 ml-0.5" />}
              </button>
            </div>
          </div>

          {/* ── Memory Space History Panel ─────────────────────────────── */}
          {showHistoryPanel && repo && (
            <MemorySpacePanel
              repoId={repo.id}
              currentSession={session}
              spaceSessions={recentSessions.filter(s => s.repo_id === repo.id)}
              forkSourceCommit={forkSourceCommit}
              mountedCheckpointId={mountedCheckpointId}
              refreshKey={checkpointRefreshKey}
              onMount={id => {
                setMountedCheckpointId(id);
                if (id !== null) {
                  // Record the last sequence number at the moment of mounting.
                  // Backend will only include turns with sequence_number > this value.
                  const lastSeq = turns.length > 0
                    ? Math.max(...turns.map(t => t.sequence_number ?? 0))
                    : -1;
                  setMountedAtSeq(lastSeq);
                } else {
                  setMountedAtSeq(null);
                }
              }}
              onFork={checkpoint => setForkTarget(checkpoint)}
              onClose={() => setShowHistoryPanel(false)}
            />
          )}

          {/* ── Fork Modal ─────────────────────────────────────────────── */}
          {forkTarget && repo && (
            <ForkModal
              spaceId={repo.id}
              checkpoint={forkTarget}
              onClose={() => setForkTarget(null)}
              onForked={newSessionId => {
                setForkTarget(null);
                navigate(`/sessions/${newSessionId}`);
              }}
            />
          )}
        </div>

      </div>
    </>
  );
}
