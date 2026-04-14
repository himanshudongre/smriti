import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getCommit, getCommitDelta, getContextFromCommit } from '../api/client';
import type { Commit, CommitDelta, TargetTool, StructuredTask } from '../types';
import { normalizeTask } from '../types';
import {
  GitCommit,
  ArrowLeft,
  Terminal,
  Bot,
  Copy,
  Check,
  MessageSquare,
  AlertTriangle,
  PlayCircle,
  GitMerge,
} from 'lucide-react';

// ── Helpers ───────────────────────────────────────────────────────────────────

function diffList(curr: string[], prev: string[]) {
  const added   = curr.filter(x => !prev.includes(x));
  const removed = prev.filter(x => !curr.includes(x));
  return { added, removed };
}

function DeltaList({ added, removed, emptyLabel }: { added: string[]; removed: string[]; emptyLabel: string }) {
  if (added.length === 0 && removed.length === 0) {
    return <p className="text-gray-600 text-xs italic">{emptyLabel}</p>;
  }
  return (
    <ul className="space-y-1">
      {added.map((item, i) => (
        <li key={`a-${i}`} className="flex items-start gap-2 text-sm">
          <span className="text-green-400 font-mono select-none">+</span>
          <span className="text-green-300">{item}</span>
        </li>
      ))}
      {removed.map((item, i) => (
        <li key={`r-${i}`} className="flex items-start gap-2 text-sm">
          <span className="text-red-400 font-mono select-none">−</span>
          <span className="text-red-300 line-through opacity-60">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function FieldBlock({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-gray-600 mb-1 font-medium">{label}</p>
      {children}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export function CommitDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [commit, setCommit]   = useState<Commit | null>(null);
  const [delta, setDelta]     = useState<CommitDelta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  // Context builder state
  const [target, setTarget]   = useState<TargetTool>('generic');
  const [context, setContext] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [copied, setCopied]   = useState(false);

  useEffect(() => {
    if (!id) return;
    setError(null);

    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Backend unreachable. Is uvicorn running on 127.0.0.1:8000?')), 8000),
    );

    Promise.race([getCommit(id), timeout])
      .then(c => {
        setCommit(c as Commit);
        // Fetch delta only if there is a parent
        if ((c as Commit).parent_commit_id) {
          return getCommitDelta(id);
        }
        return null;
      })
      .then(d => { if (d) setDelta(d); })
      .catch(err => setError(err.message || 'Commit not found'))
      .finally(() => setLoading(false));
  }, [id]);

  const buildContext = async () => {
    if (!id) return;
    try {
      setBuilding(true);
      setError(null);
      const timeout = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Context generation timed out.')), 8000),
      );
      const res = await Promise.race([getContextFromCommit(id, target), timeout]) as any;
      setContext(res.content);
      setCopied(false);
    } catch (err: any) {
      setError(err.message || 'Failed to build context');
    } finally {
      setBuilding(false);
    }
  };

  const copyToClipboard = () => {
    if (!context) return;
    navigator.clipboard.writeText(context);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ── Loading / error ───────────────────────────────────────────────────────
  if (loading) return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-500 space-y-4">
      <svg className="animate-spin h-8 w-8" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity="0.25" />
        <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" opacity="0.75" />
      </svg>
      <p className="text-sm">Loading commit…</p>
    </div>
  );
  if (!commit && !error) return <div className="text-red-500 py-10">Not Found</div>;

  // Pre-compute delta values
  const parent = delta?.parent ?? null;
  // Normalize structured tasks to their text field before diffing so
  // React can render the diff result as strings (not task objects).
  const taskTexts = (arr: (string | import('../types').StructuredTask)[] | undefined) =>
    (arr ?? []).map(t => normalizeTask(t).text);
  const taskDelta      = parent ? diffList(taskTexts(commit!.tasks), taskTexts(parent.tasks)) : null;
  const decisionDelta  = parent ? diffList(commit!.decisions,       parent.decisions)       : null;
  const questionDelta  = parent ? diffList(commit!.open_questions,  parent.open_questions)  : null;
  const summaryChanged = parent && commit!.summary !== parent.summary;
  const objectiveChanged = parent && commit!.objective !== parent.objective;

  return (
    <div className="space-y-8 animate-fade-in max-w-5xl mx-auto">
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {commit && (
        <button
          onClick={() => navigate(`/repos/${commit.repo_id}`)}
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Repo
        </button>
      )}

      {commit && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

          {/* ── LEFT COLUMN: Commit state ─────────────────────────────── */}
          <div className="space-y-6">

            {/* Commit header card */}
            <div className="card border-l-4 border-l-blue-500 pb-4">
              <div className="flex items-center gap-2 mb-2 text-blue-400 text-xs">
                <GitCommit className="w-3.5 h-3.5" />
                <code className="bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20 font-mono text-[11px]">
                  {commit.commit_hash}
                </code>
              </div>
              <h1 className="text-xl font-bold text-white tracking-tight mb-1">{commit.message}</h1>
              <div className="flex gap-3 text-xs text-gray-500 flex-wrap mt-3">
                {commit.author_agent && (
                  <span className="border border-gray-700 font-mono px-2 py-0.5 rounded capitalize">
                    {commit.author_agent}
                  </span>
                )}
                <span className="border border-gray-800 px-2 py-0.5 rounded">{commit.branch_name}</span>
                <span>{new Date(commit.created_at).toLocaleString()}</span>
              </div>
            </div>

            {/* State snapshot */}
            <div className="card space-y-5">
              <h2 className="text-sm font-medium uppercase tracking-wider text-gray-500 border-b border-gray-800 pb-2">
                State Snapshot
              </h2>

              {commit.objective && (
                <FieldBlock label="Objective">
                  <p className="text-gray-200 text-sm">{commit.objective}</p>
                </FieldBlock>
              )}

              {commit.summary && (
                <FieldBlock label="Summary">
                  <p className="text-gray-300 text-sm leading-relaxed">{commit.summary}</p>
                </FieldBlock>
              )}

              {commit.decisions.length > 0 && (
                <FieldBlock label="Decisions">
                  <ul className="list-disc pl-4 space-y-1 text-gray-400 text-sm">
                    {commit.decisions.map((d, i) => <li key={i}>{d}</li>)}
                  </ul>
                </FieldBlock>
              )}

              {commit.tasks.length > 0 && (
                <FieldBlock label="Tasks">
                  <ul className="list-disc pl-4 space-y-1.5 text-gray-400 text-sm">
                    {commit.tasks.map((raw, i) => {
                      const t: StructuredTask = normalizeTask(raw);
                      return (
                        <li key={i} className={t.status === 'done' ? 'line-through text-gray-600' : ''}>
                          {t.text}
                          {t.intent_hint && (
                            <span className="ml-1.5 text-[10px] text-blue-400 border border-blue-500/30 px-1.5 py-px rounded">
                              {t.intent_hint}
                            </span>
                          )}
                          {t.status === 'done' && (
                            <span className="ml-1.5 text-[10px] text-green-500 border border-green-500/30 px-1.5 py-px rounded">
                              done
                            </span>
                          )}
                          {t.blocked_by && (
                            <span className="ml-1.5 text-[10px] text-amber-400">
                              → blocked by: {t.blocked_by}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </FieldBlock>
              )}

              {commit.open_questions.length > 0 && (
                <FieldBlock label="Open Questions">
                  <ul className="list-disc pl-4 space-y-1 text-gray-400 text-sm">
                    {commit.open_questions.map((q, i) => <li key={i}>{q}</li>)}
                  </ul>
                </FieldBlock>
              )}

              {commit.entities.length > 0 && (
                <FieldBlock label="Entities">
                  <ul className="list-disc pl-4 space-y-1 text-gray-400 text-sm font-mono text-xs">
                    {commit.entities.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </FieldBlock>
              )}

              {!commit.objective && !commit.summary && commit.tasks.length === 0 && (
                <p className="text-gray-600 text-sm italic">No structured state recorded in this commit.</p>
              )}

              {/* Notes — additive founder annotations */}
              {commit.metadata?.notes && commit.metadata.notes.length > 0 && (
                <FieldBlock label="Notes">
                  <div className="space-y-2">
                    {commit.metadata.notes.map((n: any, i: number) => (
                      <div key={n.id || i} className="text-sm">
                        <div className="flex items-center gap-2 mb-0.5">
                          {n.kind && n.kind !== 'note' && (
                            <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full border ${
                              n.kind === 'milestone'
                                ? 'text-amber-400 border-amber-500/30 bg-amber-900/20'
                                : n.kind === 'noise'
                                  ? 'text-gray-500 border-gray-600 bg-gray-800/30'
                                  : ''
                            }`}>
                              {n.kind}
                            </span>
                          )}
                          <span className="text-[10px] text-gray-600">
                            {n.author} · {new Date(n.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-gray-300">{n.text}</p>
                      </div>
                    ))}
                  </div>
                </FieldBlock>
              )}
            </div>

            {/* Delta (state changes since parent) */}
            {parent && taskDelta && decisionDelta && questionDelta && (
              <div className="card border-gray-800 bg-gray-900/20 space-y-5">
                <h2 className="text-sm font-medium uppercase tracking-wider text-gray-500 flex items-center gap-2 border-b border-gray-800 pb-2">
                  <GitMerge className="w-4 h-4" /> What changed since parent
                </h2>

                {(summaryChanged || objectiveChanged) && (
                  <FieldBlock label={objectiveChanged ? 'Objective changed' : 'Summary changed'}>
                    <p className="text-gray-500 line-through text-xs mb-0.5">
                      {objectiveChanged ? parent.objective : parent.summary}
                    </p>
                    <p className="text-gray-200 text-sm">
                      {objectiveChanged ? commit.objective : commit.summary}
                    </p>
                  </FieldBlock>
                )}

                <FieldBlock label="Tasks">
                  <DeltaList {...taskDelta} emptyLabel="No task changes" />
                </FieldBlock>

                <FieldBlock label="Decisions">
                  <DeltaList {...decisionDelta} emptyLabel="No decision changes" />
                </FieldBlock>

                <FieldBlock label="Open Questions">
                  <DeltaList {...questionDelta} emptyLabel="No question changes" />
                </FieldBlock>
              </div>
            )}
          </div>

          {/* ── RIGHT COLUMN: Continue from this commit ────────────────── */}
          <div className="space-y-6">

            {/* Main CTA card */}
            <div className="card space-y-5">
              <div>
                <h2 className="text-xl font-semibold text-white flex items-center gap-2 mb-1">
                  <PlayCircle className="w-5 h-5 text-gray-300" />
                  Continue from this commit
                </h2>
                <p className="text-gray-500 text-sm">
                  Generate a structured handoff prompt to resume this exact state in another tool.
                </p>
              </div>

              {/* Target selector */}
              <div className="grid grid-cols-3 gap-2">
                {([
                  { id: 'generic',  label: 'Generic',  Icon: MessageSquare },
                  { id: 'claude',   label: 'Claude',   Icon: Bot },
                  { id: 'cursor',   label: 'Cursor',   Icon: Terminal },
                ] as { id: TargetTool; label: string; Icon: any }[]).map(({ id: tid, label, Icon }) => (
                  <button
                    key={tid}
                    onClick={() => setTarget(tid)}
                    className={`flex items-center justify-center gap-1.5 py-2.5 rounded border text-sm transition-all
                      ${target === tid
                        ? 'bg-white border-white text-black font-semibold'
                        : 'bg-zinc-900 border-gray-800 text-gray-400 hover:bg-gray-800 hover:text-white'
                      }`}
                  >
                    <Icon className="w-3.5 h-3.5" /> {label}
                  </button>
                ))}
              </div>

              <button
                onClick={buildContext}
                disabled={building}
                className="w-full button-primary py-3 flex items-center justify-center gap-2"
              >
                {building ? (
                  <>
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity="0.25" />
                      <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" opacity="0.75" />
                    </svg>
                    Generating…
                  </>
                ) : (
                  <>
                    <PlayCircle className="w-4 h-4" />
                    Generate {target === 'generic' ? '' : target + ' '}context
                  </>
                )}
              </button>
            </div>

            {/* Generated context output */}
            {context && (
              <div className="card border-gray-700 bg-black relative animate-fade-in group">
                <div className="absolute top-3 right-3 z-10">
                  <button
                    onClick={copyToClipboard}
                    title="Copy to clipboard"
                    className="p-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded transition-colors flex items-center gap-1 text-xs"
                  >
                    {copied
                      ? <><Check className="w-3.5 h-3.5 text-green-400" /> Copied</>
                      : <><Copy className="w-3.5 h-3.5 text-gray-400" /> Copy</>
                    }
                  </button>
                </div>
                <pre className="font-mono text-xs text-gray-300 whitespace-pre-wrap p-4 pt-10 bg-black rounded max-h-96 overflow-y-auto">
                  {context}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
