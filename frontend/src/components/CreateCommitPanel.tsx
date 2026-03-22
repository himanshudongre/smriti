import { useState } from 'react';
import { X, GitCommit, Loader2 } from 'lucide-react';
import { createCommit } from '../api/client';
import type { Commit } from '../types';
import { Field } from './Field';

interface Props {
  repoId: string;
  parentCommitId: string | null;
  onClose: () => void;
  onCreated: (commit: Commit) => void;
}

const AUTHOR_TYPES = ['llm', 'user', 'agent', 'system'] as const;

function parseLines(text: string): string[] {
  return text
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean);
}

export function CreateCommitPanel({ repoId, parentCommitId, onClose, onCreated }: Props) {
  const [message, setMessage] = useState('');
  const [authorAgent, setAuthorAgent] = useState('');
  const [authorType, setAuthorType] = useState<string>('llm');
  const [objective, setObjective] = useState('');
  const [summary, setSummary] = useState('');
  const [decisions, setDecisions] = useState('');
  const [tasks, setTasks] = useState('');
  const [openQuestions, setOpenQuestions] = useState('');
  const [entities, setEntities] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;

    try {
      setLoading(true);
      setError(null);

      const timeout = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Backend unreachable. Is uvicorn running on 127.0.0.1:8000?')), 8000),
      );

      const commit = await Promise.race([
        createCommit({
          repo_id: repoId,
          parent_commit_id: parentCommitId,
          author_agent: authorAgent || undefined,
          author_type: authorType,
          message,
          summary,
          objective,
          decisions: parseLines(decisions),
          tasks: parseLines(tasks),
          open_questions: parseLines(openQuestions),
          entities: parseLines(entities),
        }),
        timeout,
      ]) as Commit;

      onCreated(commit);
    } catch (err: any) {
      setError(err.message || 'Failed to create commit');
    } finally {
      setLoading(false);
    }
  };

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(2px)' }}
    >
      {/* Panel */}
      <div className="w-full max-w-lg h-full bg-zinc-950 border-l border-zinc-800 flex flex-col overflow-hidden animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <GitCommit className="w-4 h-4 text-zinc-400" />
            <span className="font-semibold text-white text-sm">New Commit</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-zinc-800 rounded transition-colors"
            aria-label="Close panel"
          >
            <X className="w-4 h-4 text-zinc-400" />
          </button>
        </div>

        {/* Scrollable body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
          {error && (
            <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-2">
              {error}
            </div>
          )}

          {/* Commit message */}
          <Field label="Message" required hint="Short description of this state snapshot">
            <input
              type="text"
              value={message}
              onChange={e => setMessage(e.target.value)}
              placeholder="e.g. Middleware wired, DB schema finalized"
              className="input-field"
              required
              disabled={loading}
            />
          </Field>

          {/* Author */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Author / Tool">
              <input
                type="text"
                value={authorAgent}
                onChange={e => setAuthorAgent(e.target.value)}
                placeholder="claude, cursor, user…"
                className="input-field"
                disabled={loading}
              />
            </Field>
            <Field label="Author type">
              <select
                value={authorType}
                onChange={e => setAuthorType(e.target.value)}
                className="input-field"
                disabled={loading}
              >
                {AUTHOR_TYPES.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </Field>
          </div>

          {/* Objective */}
          <Field label="Objective" hint="What are we trying to accomplish right now?">
            <input
              type="text"
              value={objective}
              onChange={e => setObjective(e.target.value)}
              placeholder="e.g. Complete auth middleware setup"
              className="input-field"
              disabled={loading}
            />
          </Field>

          {/* Summary */}
          <Field label="Summary" hint="Cumulative context — what has happened so far">
            <textarea
              value={summary}
              onChange={e => setSummary(e.target.value)}
              placeholder="We migrated from NextAuth to Lucia. The SQL adapter is configured and session handling is done..."
              rows={4}
              className="input-field resize-none"
              disabled={loading}
            />
          </Field>

          <hr className="border-zinc-800" />

          {/* Tasks */}
          <Field label="Active Tasks" hint="One task per line">
            <textarea
              value={tasks}
              onChange={e => setTasks(e.target.value)}
              placeholder={"Write generic middleware hooks\nAdd session invalidation\nVerify integration tests"}
              rows={4}
              className="input-field font-mono text-xs resize-none"
              disabled={loading}
            />
          </Field>

          {/* Decisions */}
          <Field label="Key Decisions" hint="One decision per line">
            <textarea
              value={decisions}
              onChange={e => setDecisions(e.target.value)}
              placeholder={"Use SQLite adapter for local dev\nSession auth over raw JWTs"}
              rows={3}
              className="input-field font-mono text-xs resize-none"
              disabled={loading}
            />
          </Field>

          {/* Open Questions */}
          <Field label="Open Questions" hint="One question per line">
            <textarea
              value={openQuestions}
              onChange={e => setOpenQuestions(e.target.value)}
              placeholder={"How do we handle expired sessions in the queue worker?\nShould we support multiple active sessions?"}
              rows={3}
              className="input-field font-mono text-xs resize-none"
              disabled={loading}
            />
          </Field>

          {/* Entities */}
          <Field label="Entities" hint="Key file paths, URLs, component names — one per line">
            <textarea
              value={entities}
              onChange={e => setEntities(e.target.value)}
              placeholder={"app/middleware/auth.ts\nhttps://lucia-auth.com/docs\nSessionAdapter"}
              rows={3}
              className="input-field font-mono text-xs resize-none"
              disabled={loading}
            />
          </Field>

          {/* Parent */}
          {parentCommitId && (
            <div className="text-xs text-zinc-500 border border-zinc-800 rounded px-3 py-2">
              Parent commit: <code className="text-zinc-400">{parentCommitId.slice(0, 12)}…</code>
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-zinc-800 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2.5 rounded border border-zinc-700 text-zinc-400 hover:bg-zinc-800 text-sm transition-colors"
            disabled={loading}
          >
            Cancel
          </button>
          <button
            type="submit"
            form=""
            onClick={handleSubmit as any}
            disabled={loading || !message.trim()}
            className="flex-1 button-primary py-2.5 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Committing…
              </>
            ) : (
              'Create Commit'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
