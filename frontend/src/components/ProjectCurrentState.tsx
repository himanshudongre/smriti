/**
 * ProjectCurrentState — the packaged "where is this project right now" panel.
 *
 * Renders GET /api/v5/current/spaces/{id}: current direction, counts,
 * attention signals, active work, open tasks grouped by intent, recent
 * milestones, and recent activity. Compact and scannable — the
 * founder-facing current-state surface. Empty sub-sections are elided.
 */

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { getCurrentState } from '../api/client';
import type { CurrentState } from '../types';
import { Activity, AlertTriangle, Compass, ListChecks, Loader2, Star, Zap } from 'lucide-react';

const PANEL_STYLE = {
  borderColor: 'var(--color-border, #27272a)',
  background: 'var(--color-surface, #18181b)',
} as const;

const INTENT_LABELS: Record<string, string> = {
  implement: 'Implement',
  review: 'Review',
  test: 'Test',
  docs: 'Docs',
  investigate: 'Investigate',
  other: 'Other',
};

function fmt(d: string) {
  return new Date(d).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Section({
  icon: Icon,
  title,
  iconClass,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  iconClass?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <Icon className={`w-3.5 h-3.5 ${iconClass ?? 'text-gray-500'}`} />
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function Stat({ n, label, tone }: { n: number; label: string; tone?: string }) {
  return (
    <span className="text-gray-500">
      <span className={`font-medium ${tone ?? 'text-white'}`}>{n}</span> {label}
      {n === 1 ? '' : 's'}
    </span>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ProjectCurrentState({ spaceId }: { spaceId: string }) {
  const [state, setState] = useState<CurrentState | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!spaceId) return;
    setLoading(true);
    setErr('');
    getCurrentState(spaceId)
      .then(setState)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : 'Failed to load current state'))
      .finally(() => setLoading(false));
  }, [spaceId]);

  if (loading) {
    return (
      <section className="rounded-xl border p-5 flex justify-center" style={PANEL_STYLE}>
        <Loader2 className="w-5 h-5 animate-spin text-gray-500" />
      </section>
    );
  }

  if (err || !state) {
    return (
      <section className="rounded-xl border p-5" style={PANEL_STYLE}>
        <p className="text-xs text-red-400">{err || 'No current state available.'}</p>
      </section>
    );
  }

  const dir = state.current_direction;
  const hasDirection = Boolean(dir.checkpoint_id);
  const counts = state.counts;
  const hasWarn = state.attention.some(a => a.severity === 'warn');
  const intentKeys = Object.keys(state.open_tasks_by_intent);

  return (
    <section className="rounded-xl border p-5 space-y-4" style={PANEL_STYLE}>
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-white">{state.name}</h2>
        {state.description && <p className="text-xs text-gray-500 mt-0.5">{state.description}</p>}
      </div>

      {/* Current direction */}
      {hasDirection ? (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[10px] text-gray-600 uppercase tracking-wider">
            <Compass className="w-3 h-3" />
            Current direction
          </div>
          <p className="text-sm text-gray-200">{dir.headline}</p>
          {dir.objective && <p className="text-xs text-gray-500">{dir.objective}</p>}
          <div className="flex items-center gap-2 text-[10px] text-gray-600 flex-wrap">
            {dir.author_agent && (
              <span className="font-mono border border-gray-700 px-1.5 py-px rounded text-gray-500">
                {dir.author_agent}
              </span>
            )}
            {dir.checkpoint_hash && <code className="text-blue-400">{dir.checkpoint_hash.slice(0, 7)}</code>}
            {dir.updated_at && <span>{fmt(dir.updated_at)}</span>}
          </div>
        </div>
      ) : (
        <p className="text-xs text-gray-600">No checkpoints yet — this space has no recorded direction.</p>
      )}

      {/* Counts strip */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] border-t border-b py-2"
           style={{ borderColor: 'var(--color-border, #27272a)' }}>
        <Stat n={counts.checkpoints} label="checkpoint" />
        <Stat n={counts.agents} label="agent" />
        <Stat n={counts.active_claims} label="active claim" tone="text-amber-400" />
        <Stat n={counts.active_branches} label="active branch" tone="text-purple-400" />
        <Stat n={counts.open_tasks} label="open task" tone="text-green-400" />
        <Stat n={counts.milestones} label="milestone" tone="text-amber-400" />
      </div>

      {/* Attention */}
      {state.attention.length > 0 && (
        <div
          className={`rounded-lg border px-3 py-2 ${
            hasWarn ? 'border-red-500/30 bg-red-900/10' : 'border-amber-500/30 bg-amber-900/10'
          }`}
        >
          <div
            className={`flex items-center gap-1.5 text-[11px] font-medium mb-1 ${
              hasWarn ? 'text-red-400' : 'text-amber-400'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            Needs attention
          </div>
          <ul className="space-y-0.5 text-[11px]">
            {state.attention.map((a, i) => (
              <li
                key={i}
                className={a.severity === 'warn' ? 'text-red-300/90' : 'text-amber-300/80'}
              >
                • {a.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Active work */}
      {state.active_work.length > 0 && (
        <Section icon={Zap} title="Active work" iconClass="text-amber-400">
          <div className="space-y-1.5">
            {state.active_work.map(claim => (
              <div key={claim.id} className="rounded-lg border border-amber-500/20 bg-amber-900/5 px-3 py-2">
                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                  <span className="text-[10px] text-amber-400 font-mono border border-amber-500/30 px-1.5 py-px rounded">
                    {claim.agent}
                  </span>
                  <span className="text-[10px] text-gray-500 border border-gray-700 px-1.5 py-px rounded">
                    {claim.intent_type}
                  </span>
                  <span className="text-[10px] text-gray-600">
                    on <code className="text-gray-500">{claim.branch_name}</code>
                  </span>
                  {claim.task_id && (
                    <span className="text-[10px] text-gray-600">
                      task: <code className="text-gray-500">{claim.task_id}</code>
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-300">{claim.scope}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Open tasks by intent */}
      {intentKeys.length > 0 && (
        <Section icon={ListChecks} title="Open tasks">
          <div className="space-y-2">
            {intentKeys.map(intent => (
              <div key={intent}>
                <p className="text-[9px] uppercase tracking-wider text-gray-600 mb-1">
                  {INTENT_LABELS[intent] ?? intent}
                </p>
                <ul className="space-y-0.5">
                  {state.open_tasks_by_intent[intent].map((t, i) => (
                    <li key={t.id ?? `${intent}-${i}`} className="text-[11px] text-gray-400 flex items-start gap-1.5">
                      <span className="text-gray-700 mt-px">•</span>
                      <span>
                        {t.text}
                        {t.blocked_by && (
                          <span className="text-amber-500/70"> — blocked by {t.blocked_by}</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Recent milestones */}
      {state.recent_milestones.length > 0 && (
        <Section icon={Star} title="Recent milestones" iconClass="text-amber-400">
          <ul className="space-y-1.5">
            {state.recent_milestones.map((m, i) => (
              <li key={`${m.checkpoint_id}-${i}`} className="text-[11px]">
                <div className="flex items-center gap-2 text-[10px] text-gray-600">
                  <code className="text-blue-400">{m.checkpoint_hash.slice(0, 7)}</code>
                  {m.author_agent && <span className="font-mono">{m.author_agent}</span>}
                  <span>{fmt(m.created_at)}</span>
                </div>
                <p className="text-gray-400 mt-0.5">{m.note}</p>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Recent activity */}
      {state.recent_activity.length > 0 && (
        <Section icon={Activity} title="Recent activity">
          <ul className="space-y-1">
            {state.recent_activity.map(a => (
              <li key={a.checkpoint_id} className="flex items-center gap-2 text-[11px]">
                <code className="text-blue-400 flex-shrink-0">{a.checkpoint_hash.slice(0, 7)}</code>
                {a.has_milestone && <Star className="w-3 h-3 text-amber-400 flex-shrink-0" />}
                <span className="text-gray-400 truncate flex-1">{a.message}</span>
                {a.branch_name !== 'main' && (
                  <span className="text-[9px] text-purple-400 bg-purple-500/10 border border-purple-500/30 px-1.5 py-px rounded flex-shrink-0">
                    {a.branch_name}
                  </span>
                )}
                {a.author_agent && (
                  <span className="text-[9px] text-gray-600 font-mono flex-shrink-0">{a.author_agent}</span>
                )}
                <span className="text-[10px] text-gray-600 flex-shrink-0">{fmt(a.created_at)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </section>
  );
}
