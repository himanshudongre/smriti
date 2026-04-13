/**
 * LineagePage — branch tree view for a Memory Space.
 *
 * Mental model:
 *   - Checkpoints are the durable lineage graph nodes.
 *   - Sessions are temporary runtimes — shown as secondary metadata.
 *
 * Layout:
 *   - Every branch (main + forks) renders its own checkpoint chain.
 *   - Selecting any two checkpoints, across any branches, enables Compare.
 *   - If a fork branch has no checkpoints yet the active session is shown
 *     as a placeholder so the branch is still visible.
 *   - "You are here" marker attaches to the most recent checkpoint on the
 *     active session's branch, or to the session card when no checkpoints
 *     exist yet.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { getLineage, getSpaceState, compareCheckpoints, forkSession } from '../api/client';
import type {
  ActiveClaimSummary,
  CheckpointNode,
  SessionNode,
  LineageResponse,
  CompareResponse,
  StructuredTask,
} from '../types';
import { normalizeTask } from '../types';
import { GitBranch, GitCommit, Loader2, X, ArrowLeft, Zap } from 'lucide-react';

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(d: string) {
  return new Date(d).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getCheckpointNoteBadge(checkpoint: CheckpointNode) {
  const kinds = checkpoint.note_kinds ?? [];
  const plural = checkpoint.note_count !== 1 ? 's' : '';
  const kindSummary = kinds.length > 0 ? kinds.join(' + ') : 'note';

  if (kinds.length > 1) {
    return {
      label: 'mix',
      title: `${checkpoint.note_count} note${plural} · ${kindSummary}`,
      className: 'text-sky-300 bg-sky-950/30 border border-sky-500/30',
    };
  }

  if (kinds.includes('milestone')) {
    return {
      label: '★',
      title: `${checkpoint.note_count} note${plural} · milestone`,
      className: 'text-amber-400 bg-amber-900/20 border border-amber-500/30',
    };
  }

  if (kinds.includes('noise')) {
    return {
      label: '◌',
      title: `${checkpoint.note_count} note${plural} · noise`,
      className: 'text-gray-500 bg-gray-800/30 border border-gray-700',
    };
  }

  return {
    label: '●',
    title: `${checkpoint.note_count} note${plural} · note`,
    className: 'text-gray-400 bg-gray-800/30 border border-gray-700',
  };
}

// ── Compare Panel ─────────────────────────────────────────────────────────────

function ComparePanel({
  aId,
  bId,
  checkpoints,
  onClose,
}: {
  aId: string;
  bId: string;
  checkpoints: CheckpointNode[];
  onClose: () => void;
}) {
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    compareCheckpoints(aId, bId)
      .then(setResult)
      .catch(e => setErr(e.message || 'Compare failed'))
      .finally(() => setLoading(false));
  }, [aId, bId]);

  const a = checkpoints.find(c => c.id === aId);
  const b = checkpoints.find(c => c.id === bId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.75)' }}>
      <div
        className="w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-xl border p-6 space-y-5"
        style={{ background: 'var(--color-surface, #18181b)', borderColor: 'var(--color-border, #27272a)' }}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <GitCommit className="w-4 h-4 text-blue-400" />
            Compare checkpoints
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Checkpoint labels */}
        <div className="grid grid-cols-2 gap-4 text-[11px]">
          {[a, b].map((c, i) => c && (
            <div key={i} className={`rounded-lg border px-3 py-2 ${i === 0 ? 'border-blue-500/30 bg-blue-900/10' : 'border-green-500/30 bg-green-900/10'}`}>
              <div className="flex items-center gap-2">
                <code className={`${i === 0 ? 'text-blue-400' : 'text-green-400'} font-mono`}>{c.commit_hash.slice(0, 7)}</code>
                <span className="text-gray-600 text-[9px] bg-zinc-800 px-1.5 py-0.5 rounded">{c.branch_name}</span>
              </div>
              <span className="text-gray-400 mt-0.5 block">{c.message}</span>
              <p className="text-gray-600 mt-0.5">{fmt(c.created_at)}</p>
            </div>
          ))}
        </div>

        {loading && (
          <div className="flex justify-center py-6">
            <Loader2 className="w-5 h-5 animate-spin text-gray-500" />
          </div>
        )}
        {err && <p className="text-xs text-red-400">{err}</p>}

        {result && (
          <div className="space-y-5">
            {/* Summary */}
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Summary</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="text-xs text-gray-300 bg-blue-900/10 border border-blue-500/20 rounded-lg px-3 py-2 leading-relaxed">{result.diff.summary_a || <span className="text-gray-600 italic">—</span>}</div>
                <div className="text-xs text-gray-300 bg-green-900/10 border border-green-500/20 rounded-lg px-3 py-2 leading-relaxed">{result.diff.summary_b || <span className="text-gray-600 italic">—</span>}</div>
              </div>
            </div>

            {/* Objective */}
            {(result.diff.objective_a || result.diff.objective_b) && (
              <div>
                <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Objective</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="text-xs text-gray-300 bg-blue-900/10 border border-blue-500/20 rounded-lg px-3 py-2">{result.diff.objective_a || <span className="text-gray-600 italic">—</span>}</div>
                  <div className="text-xs text-gray-300 bg-green-900/10 border border-green-500/20 rounded-lg px-3 py-2">{result.diff.objective_b || <span className="text-gray-600 italic">—</span>}</div>
                </div>
              </div>
            )}

            {/* Decisions diff */}
            <DiffSection
              label="Decisions"
              onlyA={result.diff.decisions_only_a}
              onlyB={result.diff.decisions_only_b}
              shared={result.diff.decisions_shared}
            />

            {/* Tasks diff */}
            <DiffSection
              label="Tasks"
              onlyA={result.diff.tasks_only_a}
              onlyB={result.diff.tasks_only_b}
              shared={result.diff.tasks_shared}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function DiffSection({
  label,
  onlyA,
  onlyB,
  shared,
}: {
  label: string;
  onlyA: string[];
  onlyB: string[];
  shared: string[];
}) {
  if (onlyA.length === 0 && onlyB.length === 0 && shared.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">{label}</p>
      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <div className="space-y-1">
          <p className="text-[9px] uppercase tracking-wider text-blue-500 mb-1">A only</p>
          {onlyA.length === 0 ? <p className="text-gray-700 italic">none</p> : onlyA.map((d, i) => (
            <div key={i} className="text-blue-300 bg-blue-900/10 border border-blue-500/20 rounded px-2 py-1">{d}</div>
          ))}
        </div>
        <div className="space-y-1">
          <p className="text-[9px] uppercase tracking-wider text-gray-500 mb-1">Shared</p>
          {shared.length === 0 ? <p className="text-gray-700 italic">none</p> : shared.map((d, i) => (
            <div key={i} className="text-gray-400 bg-zinc-800 border border-gray-700 rounded px-2 py-1">{d}</div>
          ))}
        </div>
        <div className="space-y-1">
          <p className="text-[9px] uppercase tracking-wider text-green-500 mb-1">B only</p>
          {onlyB.length === 0 ? <p className="text-gray-700 italic">none</p> : onlyB.map((d, i) => (
            <div key={i} className="text-green-300 bg-green-900/10 border border-green-500/20 rounded px-2 py-1">{d}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Fork Modal (inline) ───────────────────────────────────────────────────────

function ForkModal({
  spaceId,
  checkpoint,
  onClose,
  onForked,
}: {
  spaceId: string;
  checkpoint: CheckpointNode;
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
      style={{ background: 'rgba(0,0,0,0.75)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="w-full max-w-sm rounded-xl border p-6 space-y-4"
        style={{ background: 'var(--color-surface, #18181b)', borderColor: 'var(--color-border, #27272a)' }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className="w-4 h-4 text-purple-400" />
            <h2 className="text-sm font-semibold text-white">Fork from checkpoint</h2>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X className="w-4 h-4" /></button>
        </div>

        <div className="text-[11px] text-gray-500 space-y-0.5">
          <p>Branching from:</p>
          <div className="flex items-center gap-2">
            <code className="text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">{checkpoint.commit_hash.slice(0, 7)}</code>
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
            style={{ borderColor: 'var(--color-border, #27272a)' }}
          />
        </div>

        {err && <p className="text-xs text-red-400">{err}</p>}

        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onClose}
            className="text-xs px-3 py-1.5 rounded-md border text-gray-400 hover:text-white transition-colors"
            style={{ borderColor: 'var(--color-border, #27272a)' }}
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

// ── CheckpointCard ────────────────────────────────────────────────────────────

function CheckpointCard({
  checkpoint,
  isSelected,
  onSelect,
  onFork,
}: {
  checkpoint: CheckpointNode;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onFork: (c: CheckpointNode) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const noteBadge = checkpoint.note_count > 0 ? getCheckpointNoteBadge(checkpoint) : null;

  return (
    <div
      className={`rounded-lg border transition-colors ${
        isSelected ? 'border-blue-500/60 bg-blue-900/10' : 'border-gray-800 bg-zinc-900 hover:border-gray-700'
      }`}
    >
      <div className="px-3 py-2.5 flex items-start gap-2">
        <div
          className="w-5 h-5 rounded-full border-2 flex-shrink-0 mt-0.5 cursor-pointer flex items-center justify-center"
          style={{ borderColor: isSelected ? '#3b82f6' : '#3f3f46' }}
          onClick={() => onSelect(checkpoint.id)}
        >
          {isSelected && <div className="w-2 h-2 rounded-full bg-blue-500" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <code className="text-[10px] text-blue-400 font-mono">{checkpoint.commit_hash.slice(0, 7)}</code>
            {checkpoint.author_agent && (
              <span className="text-[10px] text-gray-500 font-mono border border-gray-700 px-1.5 py-px rounded">
                {checkpoint.author_agent}
              </span>
            )}
            <span className="text-[10px] text-gray-600">{fmt(checkpoint.created_at)}</span>
            {noteBadge && (
              <span
                className={`text-[9px] font-medium px-1 py-px rounded ${noteBadge.className}`}
                title={noteBadge.title}
              >
                {noteBadge.label}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-300 font-medium truncate">{checkpoint.message}</p>
          {expanded && (
            <div className="mt-2 space-y-1.5 text-[11px]">
              {checkpoint.objective && (
                <div>
                  <span className="text-gray-600 uppercase tracking-wider text-[9px]">Objective </span>
                  <span className="text-gray-400">{checkpoint.objective}</span>
                </div>
              )}
              {checkpoint.summary && (
                <p className="text-gray-500 leading-relaxed">{checkpoint.summary}</p>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1 flex-shrink-0">
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-[10px] text-gray-600 hover:text-gray-300 transition-colors px-2 py-0.5 rounded border border-gray-800 hover:bg-zinc-800"
          >
            {expanded ? 'Hide' : 'Info'}
          </button>
          <button
            onClick={() => onFork(checkpoint)}
            className="text-[10px] text-gray-600 hover:text-purple-300 transition-colors px-2 py-0.5 rounded border border-gray-800 hover:border-purple-500/40 hover:bg-purple-900/20 flex items-center gap-1"
          >
            <GitBranch className="w-3 h-3" />
            Fork
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Active Session Chip ───────────────────────────────────────────────────────

function ActiveSessionChip({
  session,
  isHere,
  sessionRef,
  onClick,
}: {
  session: SessionNode;
  isHere: boolean;
  sessionRef?: React.RefObject<HTMLDivElement | null>;
  onClick: () => void;
}) {
  return (
    <div
      ref={isHere ? sessionRef : undefined}
      className={`mt-2 rounded-lg border px-3 py-2 cursor-pointer transition-colors ${
        isHere
          ? 'border-purple-500/40 bg-purple-900/10 hover:border-purple-400/60'
          : 'border-gray-800 bg-zinc-900/50 hover:border-gray-700'
      }`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[9px] text-purple-500">▶</span>
          <p className="text-xs text-gray-400 truncate">{session.title || 'Untitled session'}</p>
          {isHere && (
            <span className="flex-shrink-0 text-[9px] font-medium text-purple-400 bg-purple-500/15 border border-purple-500/30 px-1.5 py-0.5 rounded-full">
              ← you are here
            </span>
          )}
        </div>
        <span className="text-[10px] text-gray-600 ml-2 flex-shrink-0">{fmt(session.created_at)}</span>
      </div>
    </div>
  );
}

// ── Branch Section ────────────────────────────────────────────────────────────

function BranchSection({
  branchName,
  checkpoints,
  sessions,
  currentSessionId,
  selected,
  onSelect,
  onFork,
  onNavigate,
  sessionRef,
  isMain,
  disposition,
}: {
  branchName: string;
  checkpoints: CheckpointNode[];
  sessions: SessionNode[];
  currentSessionId: string | null;
  selected: string[];
  onSelect: (id: string) => void;
  onFork: (c: CheckpointNode) => void;
  onNavigate: (sessionId: string) => void;
  sessionRef: React.RefObject<HTMLDivElement | null>;
  isMain: boolean;
  disposition?: string;
}) {
  const mostRecentCheckpoint = checkpoints[checkpoints.length - 1];
  const activeSession = sessions.find(s => s.id === currentSessionId) ?? sessions[0] ?? null;

  // For fork branches: find the fork source checkpoint to display the fork point
  const forkSourceId = isMain ? null : (sessions[0]?.forked_from_checkpoint_id ?? checkpoints[0]?.parent_checkpoint_id ?? null);

  const lineColor = isMain ? 'bg-blue-900/30' : 'bg-purple-900/30';
  const dotColor = isMain ? 'bg-blue-500' : 'bg-purple-500';
  const labelColor = isMain ? 'text-gray-400' : 'text-purple-300';

  return (
    <section>
      {/* Branch header */}
      <div className="flex items-center gap-2 mb-4">
        <div className={`w-2 h-2 rounded-full ${dotColor}`} />
        {!isMain && <GitBranch className="w-3 h-3 text-purple-500" />}
        <h2 className={`text-xs font-semibold uppercase tracking-wider ${labelColor}`}>{branchName}</h2>
        {!isMain && forkSourceId && (
          <span className="text-[10px] text-gray-600">
            forked from <code className="text-blue-400 font-mono">{forkSourceId.slice(0, 7)}</code>
          </span>
        )}
        {!isMain && disposition && disposition !== 'active' && (
          <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full border ${
            disposition === 'integrated'
              ? 'text-green-400 border-green-500/30 bg-green-900/20'
              : disposition === 'abandoned'
                ? 'text-red-400 border-red-500/30 bg-red-900/20'
                : 'text-gray-400 border-gray-600 bg-gray-800/30'
          }`}>
            {disposition}
          </span>
        )}
      </div>

      {checkpoints.length > 0 ? (
        // Checkpoint-centric view
        <div className="relative ml-3">
          <div className={`absolute left-2 top-3 bottom-3 w-px ${lineColor}`} />
          <div className="space-y-3 ml-7">
            {checkpoints.map((c, idx) => {
              const isLast = idx === checkpoints.length - 1;
              return (
                <div key={c.id}>
                  <CheckpointCard
                    checkpoint={c}
                    isSelected={selected.includes(c.id)}
                    onSelect={onSelect}
                    onFork={onFork}
                  />
                  {/* Attach active session chip below the most recent checkpoint */}
                  {isLast && activeSession && (
                    <ActiveSessionChip
                      session={activeSession}
                      isHere={activeSession.id === currentSessionId}
                      sessionRef={sessionRef}
                      onClick={() => onNavigate(activeSession.id)}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        // No checkpoints yet — show session cards as placeholder
        <div className="ml-5 space-y-2">
          {sessions.length === 0 ? (
            <p className="text-sm text-gray-600">No checkpoints yet.</p>
          ) : (
            sessions.map(s => {
              const isHere = s.id === currentSessionId;
              return (
                <div
                  key={s.id}
                  ref={isHere ? sessionRef : undefined}
                  className={`rounded-lg border px-3 py-2.5 transition-colors cursor-pointer ${
                    isHere
                      ? 'border-purple-500/60 bg-purple-900/10 hover:border-purple-400/60'
                      : 'border-gray-800 bg-zinc-900 hover:border-gray-700'
                  }`}
                  onClick={() => onNavigate(s.id)}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-xs text-gray-300">{s.title || 'Untitled session'}</p>
                        {isHere && (
                          <span className="text-[9px] font-medium text-purple-400 bg-purple-500/15 border border-purple-500/30 px-1.5 py-0.5 rounded-full">
                            ← you are here
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-gray-600 mt-0.5">{fmt(s.created_at)} · no checkpoints yet</p>
                    </div>
                    <span className="text-[10px] text-gray-600 bg-zinc-800 px-2 py-0.5 rounded">Open →</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Main branch: also list all sessions below the checkpoint chain */}
      {isMain && sessions.length > 0 && checkpoints.length > 0 && (
        <div className="mt-6 ml-3">
          <p className="text-[10px] uppercase tracking-wider text-gray-700 mb-2">Sessions on main</p>
          <div className="ml-7 space-y-2">
            {sessions.map(s => {
              const isHere = s.id === currentSessionId;
              // Skip the one already shown as the active chip (avoid duplicate)
              if (isHere && mostRecentCheckpoint) return null;
              return (
                <div
                  key={s.id}
                  ref={isHere ? sessionRef : undefined}
                  className={`rounded-lg border px-3 py-2 transition-colors cursor-pointer ${
                    isHere
                      ? 'border-blue-500/60 bg-blue-900/10 hover:border-blue-400/60'
                      : 'border-gray-800 bg-zinc-900 hover:border-gray-700'
                  }`}
                  onClick={() => onNavigate(s.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <p className="text-xs text-gray-300">{s.title || 'Untitled session'}</p>
                      {isHere && (
                        <span className="text-[9px] font-medium text-blue-400 bg-blue-500/15 border border-blue-500/30 px-1.5 py-0.5 rounded-full">
                          ← you are here
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-gray-600">{fmt(s.created_at)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function LineagePage() {
  const { spaceId } = useParams<{ spaceId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const currentSessionId = searchParams.get('session');

  const [lineage, setLineage] = useState<LineageResponse | null>(null);
  const [activeClaims, setActiveClaims] = useState<ActiveClaimSummary[]>([]);
  const [spaceState, setSpaceState] = useState<import('../types').SpaceStateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  // Multi-select for compare (max 2)
  const [selected, setSelected] = useState<string[]>([]);

  // Active modal states
  const [forkTarget, setForkTarget] = useState<CheckpointNode | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);

  // Ref for scroll-to-current-session
  const currentSessionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!spaceId) return;
    Promise.all([
      getLineage(spaceId),
      getSpaceState(spaceId).catch(() => null),
    ])
      .then(([lin, state]) => {
        setLineage(lin);
        setSpaceState(state);
        setActiveClaims(state?.active_claims ?? []);
      })
      .catch(e => setErr(e.message || 'Failed to load lineage'))
      .finally(() => setLoading(false));
  }, [spaceId]);

  // Scroll to current session once lineage is loaded
  useEffect(() => {
    if (currentSessionRef.current) {
      currentSessionRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [lineage, currentSessionId]);

  const handleSelect = (id: string) => {
    setSelected(prev => {
      if (prev.includes(id)) return prev.filter(x => x !== id);
      if (prev.length >= 2) return [prev[1], id]; // rotate: drop oldest
      return [...prev, id];
    });
  };

  // ── Derived data ────────────────────────────────────────────────────────────

  // Group checkpoints by branch, sorted oldest-first within each branch
  const checkpointsByBranch = new Map<string, CheckpointNode[]>();
  (lineage?.checkpoints ?? []).forEach(c => {
    const br = c.branch_name || 'main';
    if (!checkpointsByBranch.has(br)) checkpointsByBranch.set(br, []);
    checkpointsByBranch.get(br)!.push(c);
  });
  checkpointsByBranch.forEach((arr, br) => {
    checkpointsByBranch.set(
      br,
      [...arr].sort((a, b) => +new Date(a.created_at) - +new Date(b.created_at)),
    );
  });

  // Group sessions by branch
  const sessionsByBranch = new Map<string, SessionNode[]>();
  (lineage?.sessions ?? []).forEach(s => {
    const br = s.branch_name || 'main';
    if (!sessionsByBranch.has(br)) sessionsByBranch.set(br, []);
    sessionsByBranch.get(br)!.push(s);
  });

  // All fork branch names — union of branches from checkpoints AND sessions
  const forkBranchNames = new Set<string>();
  (lineage?.checkpoints ?? []).forEach(c => { if (c.branch_name && c.branch_name !== 'main') forkBranchNames.add(c.branch_name); });
  (lineage?.sessions ?? []).forEach(s => { if (s.branch_name && s.branch_name !== 'main') forkBranchNames.add(s.branch_name); });
  const forkBranches = Array.from(forkBranchNames).sort();

  const totalCheckpoints = lineage?.checkpoints.length ?? 0;
  const totalSessions = lineage?.sessions.length ?? 0;

  return (
    <div className="min-h-screen" style={{ background: 'var(--color-bg, #09090b)', color: 'var(--color-text, #e4e4e7)' }}>
      {/* Header */}
      <header className="sticky top-0 z-40 border-b" style={{ background: 'rgba(9,9,11,0.9)', backdropFilter: 'blur(12px)', borderColor: 'var(--color-border, #27272a)' }}>
        <div className="max-w-5xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(-1)}
              className="text-gray-500 hover:text-white transition-colors flex items-center gap-1 text-sm"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-purple-400" />
              <h1 className="text-sm font-semibold text-white">Branch Tree</h1>
            </div>
            {lineage && (
              <span className="text-[11px] text-gray-600">
                {totalCheckpoints} checkpoint{totalCheckpoints !== 1 ? 's' : ''}
                {' · '}
                {totalSessions} session{totalSessions !== 1 ? 's' : ''}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {selected.length === 2 && (
              <button
                onClick={() => setCompareOpen(true)}
                className="text-xs px-3 py-1.5 rounded-md border font-medium transition-colors flex items-center gap-1.5"
                style={{ borderColor: '#3b82f6', color: '#93c5fd', background: 'rgba(59,130,246,0.1)' }}
              >
                Compare selected
              </button>
            )}
            {selected.length === 1 && (
              <span className="text-[11px] text-gray-600">Select one more checkpoint to compare</span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {loading && (
          <div className="flex justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-gray-500" />
          </div>
        )}
        {err && <p className="text-sm text-red-400">{err}</p>}

        {lineage && !loading && (
          <div className="space-y-10">
            {/* Current-state summary panel */}
            {spaceState && (
              <section className="rounded-xl border p-5 space-y-4" style={{ borderColor: 'var(--color-border, #27272a)', background: 'var(--color-surface, #18181b)' }}>
                {/* Project header */}
                <div>
                  <h2 className="text-base font-semibold text-white">
                    {spaceState.space.name}
                  </h2>
                  {spaceState.space.description && (
                    <p className="text-xs text-gray-500 mt-0.5">{spaceState.space.description}</p>
                  )}
                </div>

                {/* Current direction */}
                {spaceState.commit && (
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-gray-600 uppercase tracking-wider">Current direction</span>
                    </div>
                    <p className="text-sm text-gray-200">{spaceState.commit.message}</p>
                    {spaceState.commit.objective && (
                      <p className="text-xs text-gray-500">{spaceState.commit.objective}</p>
                    )}
                    <div className="flex items-center gap-2 text-[10px] text-gray-600">
                      {spaceState.commit.author_agent && (
                        <span className="font-mono border border-gray-700 px-1.5 py-px rounded text-gray-500">
                          {spaceState.commit.author_agent}
                        </span>
                      )}
                      <span>{fmt(spaceState.commit.created_at)}</span>
                      <code className="text-blue-400">{spaceState.commit.commit_hash?.slice(0, 7)}</code>
                    </div>
                  </div>
                )}

                {/* Status bar */}
                <div className="flex items-center gap-4 flex-wrap text-[11px]">
                  <span className="text-gray-500">
                    <span className="text-white font-medium">{lineage.checkpoints.length}</span> checkpoint{lineage.checkpoints.length !== 1 ? 's' : ''}
                  </span>
                  {(spaceState.active_branches?.length ?? 0) > 0 && (
                    <span className="text-gray-500">
                      <span className="text-purple-400 font-medium">{spaceState.active_branches.length}</span> active branch{spaceState.active_branches.length !== 1 ? 'es' : ''}
                    </span>
                  )}
                  {activeClaims.length > 0 && (
                    <span className="text-gray-500">
                      <span className="text-amber-400 font-medium">{activeClaims.length}</span> active claim{activeClaims.length !== 1 ? 's' : ''}
                    </span>
                  )}
                  {spaceState.divergence && (spaceState.divergence.pairs?.length ?? 0) > 0 && (
                    <span className="text-red-400 font-medium flex items-center gap-1">
                      ⚠ Divergence detected
                    </span>
                  )}
                  {(spaceState.commit?.tasks?.length ?? 0) > 0 && (() => {
                    const tasks = (spaceState.commit.tasks ?? []).map(normalizeTask);
                    const openCount = tasks.filter((t: StructuredTask) => !t.status || t.status === 'open').length;
                    const doneCount = tasks.filter((t: StructuredTask) => t.status === 'done').length;
                    return (
                      <span className="text-gray-500">
                        <span className="text-green-400 font-medium">{openCount}</span> open task{openCount !== 1 ? 's' : ''}
                        {doneCount > 0 && (
                          <>, <span className="text-gray-600">{doneCount} done</span></>
                        )}
                      </span>
                    );
                  })()}
                </div>

                {/* Needs attention signal */}
                {(() => {
                  const reasons: string[] = [];
                  if (spaceState.divergence && (spaceState.divergence.pairs?.length ?? 0) > 0)
                    reasons.push('Branch divergence needs resolution');
                  if (activeClaims.length > 0)
                    reasons.push(`${activeClaims.length} agent${activeClaims.length !== 1 ? 's' : ''} working — check before starting new work`);
                  if ((spaceState.commit?.open_questions?.length ?? 0) > 0)
                    reasons.push(`${spaceState.commit.open_questions.length} open question${spaceState.commit.open_questions.length !== 1 ? 's' : ''} from latest checkpoint`);
                  if (reasons.length === 0) return null;
                  return (
                    <div className="rounded-lg border border-amber-500/30 bg-amber-900/10 px-3 py-2">
                      <div className="flex items-center gap-2 text-[11px] text-amber-400 font-medium mb-1">
                        <span>⚡ Needs attention</span>
                      </div>
                      <ul className="text-[11px] text-amber-300/80 space-y-0.5">
                        {reasons.map((r, i) => (
                          <li key={i}>• {r}</li>
                        ))}
                      </ul>
                    </div>
                  );
                })()}
              </section>
            )}

            {/* Active work claims */}
            {activeClaims.length > 0 && (
              <section>
                <div className="flex items-center gap-2 mb-3">
                  <Zap className="w-4 h-4 text-amber-400" />
                  <h2 className="text-sm font-semibold text-white">Active work</h2>
                  <span className="text-[10px] text-gray-600">{activeClaims.length} claim{activeClaims.length !== 1 ? 's' : ''}</span>
                </div>
                <div className="space-y-2">
                  {activeClaims.map(claim => (
                    <div
                      key={claim.id}
                      className="rounded-lg border border-amber-500/30 bg-amber-900/10 px-4 py-3"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] text-amber-400 font-mono border border-amber-500/30 px-1.5 py-px rounded">
                          {claim.agent}
                        </span>
                        <span className="text-[10px] text-gray-500 border border-gray-700 px-1.5 py-px rounded">
                          {claim.intent_type}
                        </span>
                        <span className="text-[10px] text-gray-600">
                          on <code className="text-gray-500">{claim.branch_name}</code>
                          {claim.base_commit_hash && (
                            <> from <code className="text-blue-400">{claim.base_commit_hash}</code></>
                          )}
                        </span>
                      </div>
                      <p className="text-xs text-gray-300">{claim.scope}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Main branch */}
            <BranchSection
              branchName="main"
              checkpoints={checkpointsByBranch.get('main') ?? []}
              sessions={sessionsByBranch.get('main') ?? []}
              currentSessionId={currentSessionId}
              selected={selected}
              onSelect={handleSelect}
              onFork={setForkTarget}
              onNavigate={id => navigate(`/sessions/${id}`)}
              sessionRef={currentSessionRef}
              isMain={true}
            />

            {/* Fork branches */}
            {forkBranches.map(branch => {
              // Derive disposition from sessions on this branch.
              // If any session is "active", the branch is active.
              // Otherwise use the most recent session's disposition.
              const branchSessions = sessionsByBranch.get(branch) ?? [];
              const hasActive = branchSessions.some(s => (s.branch_disposition || 'active') === 'active');
              const disposition = hasActive
                ? 'active'
                : (branchSessions[0]?.branch_disposition || 'active');

              return (
                <BranchSection
                  key={branch}
                  branchName={branch}
                  checkpoints={checkpointsByBranch.get(branch) ?? []}
                  sessions={branchSessions}
                  currentSessionId={currentSessionId}
                  selected={selected}
                  onSelect={handleSelect}
                  onFork={setForkTarget}
                  onNavigate={id => navigate(`/sessions/${id}`)}
                  sessionRef={currentSessionRef}
                  isMain={false}
                  disposition={disposition}
                />
              );
            })}
          </div>
        )}
      </main>

      {/* Fork Modal */}
      {forkTarget && spaceId && (
        <ForkModal
          spaceId={spaceId}
          checkpoint={forkTarget}
          onClose={() => setForkTarget(null)}
          onForked={newSessionId => {
            setForkTarget(null);
            navigate(`/sessions/${newSessionId}`);
          }}
        />
      )}

      {/* Compare Modal */}
      {compareOpen && selected.length === 2 && lineage && (
        <ComparePanel
          aId={selected[0]}
          bId={selected[1]}
          checkpoints={lineage.checkpoints}
          onClose={() => setCompareOpen(false)}
        />
      )}
    </div>
  );
}
