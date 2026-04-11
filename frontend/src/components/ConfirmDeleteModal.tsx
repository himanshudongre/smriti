import { useState } from 'react';
import { Trash2, Loader2, GitCommit, GitBranch, X } from 'lucide-react';

/**
 * A dependent is something that references the object being deleted.
 * The backend returns three kinds for checkpoint delete; space delete
 * does not populate this at all.
 */
export type Dependent = {
  kind: 'child_commit' | 'forked_session' | 'seeded_session';
  id: string;
  label: string;
};

export type Dependents = {
  checkpoint_id?: string;
  child_commits: Dependent[];
  forked_sessions: Dependent[];
  seeded_sessions: Dependent[];
  blocking_count: number;
};

type Props = {
  /** Title shown in the modal header, e.g. "Delete space 'foo'?". */
  title: string;
  /** Body text explaining the consequences. May contain newlines. */
  body: string;
  /** Optional override for the primary action label. Defaults to "Delete". */
  confirmLabel?: string;
  /**
   * When null/undefined, the modal is in its first-pass state: plain body,
   * plain Delete button.
   *
   * When populated with dependents the modal is in its cascade-confirm state:
   * it renders the blocking list and a "I understand..." checkbox that must
   * be ticked before the Delete button re-enables. The label switches to
   * "Delete subtree".
   *
   * The modal itself is stateless about which pass it's in — the parent
   * catches the 409 ApiError, reads `error.detail.dependents`, and re-passes
   * the modal with the new dependents prop to move to the second pass.
   */
  dependents?: Dependents | null;
  onClose: () => void;
  /** Returns a promise so the modal can show a loading spinner while the
   * caller hits the backend. Parent decides whether to close on success. */
  onConfirm: (cascade: boolean) => Promise<void>;
};

export function ConfirmDeleteModal({
  title,
  body,
  confirmLabel,
  dependents,
  onClose,
  onConfirm,
}: Props) {
  const [cascadeConfirmed, setCascadeConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const blocking = dependents?.blocking_count ?? 0;
  const inCascadeMode = blocking > 0;
  const disabled = loading || (inCascadeMode && !cascadeConfirmed);

  const handleConfirm = async () => {
    setErr(null);
    setLoading(true);
    try {
      await onConfirm(inCascadeMode);
      // Parent is responsible for calling onClose() in the success path
      // because it may also want to refresh state, navigate, etc. We stay
      // mounted in case the parent chooses to leave us open (e.g. to
      // transition us into cascade-confirm mode on a 409).
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-md bg-zinc-950 border border-gray-800 rounded-xl shadow-2xl overflow-hidden my-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <Trash2 className="w-4 h-4 text-red-400" /> {title}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{body}</p>

          {/* Cascade callout — second pass only */}
          {inCascadeMode && (
            <div className="border border-amber-500/30 bg-amber-500/5 rounded-lg p-3 space-y-2">
              <p className="text-xs uppercase tracking-wider text-amber-400">
                This will also delete:
              </p>
              <ul className="text-xs text-gray-400 space-y-0.5">
                {dependents!.child_commits.map(d => (
                  <li key={d.id} className="flex items-center gap-1.5">
                    <GitCommit className="w-3 h-3 text-blue-400/70 flex-shrink-0" />
                    <span className="truncate">{d.label}</span>
                  </li>
                ))}
                {dependents!.forked_sessions.map(d => (
                  <li key={d.id} className="flex items-center gap-1.5">
                    <GitBranch className="w-3 h-3 text-purple-400/70 flex-shrink-0" />
                    <span className="truncate">{d.label}</span>
                  </li>
                ))}
              </ul>
              <label className="flex items-start gap-2 text-xs text-amber-200 cursor-pointer pt-2">
                <input
                  type="checkbox"
                  checked={cascadeConfirmed}
                  onChange={e => setCascadeConfirmed(e.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  I understand that {blocking} item{blocking === 1 ? '' : 's'} will be
                  deleted along with this checkpoint
                </span>
              </label>
            </div>
          )}

          {/* Informational seeded_sessions — never blocks */}
          {dependents && dependents.seeded_sessions.length > 0 && (
            <p className="text-[11px] text-gray-500">
              {dependents.seeded_sessions.length} session
              {dependents.seeded_sessions.length === 1 ? ' was' : 's were'} opened
              from this checkpoint; they will keep their materialised turns but lose
              the seed pointer.
            </p>
          )}

          {err && <p className="text-red-400 text-sm">{err}</p>}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-800 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="text-sm text-gray-400 hover:text-white px-3 py-1.5 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={disabled}
            className="bg-red-600 hover:bg-red-500 text-white text-sm font-medium px-4 py-1.5 rounded-md flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}
            {inCascadeMode ? 'Delete subtree' : confirmLabel ?? 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDeleteModal;
