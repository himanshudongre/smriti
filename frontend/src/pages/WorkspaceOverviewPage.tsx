import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  FolderOpen,
  GitBranch,
  GitCommit,
  Loader2,
  MessageSquare,
  MoreVertical,
  Plus,
  RotateCcw,
  Settings2,
  Trash2,
} from 'lucide-react';
import {
  deleteRepo,
  getRecentSessionsGeneric,
  getRepos,
  getSpaceHead,
} from '../api/client';
import type { ChatSession, HeadState, Repo } from '../types';
import { ConfirmDeleteModal } from '../components/ConfirmDeleteModal';

/**
 * Landing page focused on resume.
 *
 * The previous behavior auto-created a blank session on '/', which hid any
 * orientation signal and made cold returns feel worse than a generic chat
 * history. This page instead surfaces the most recent checkpointed work as a
 * resume card, followed by recent spaces, so a returning user can click once
 * to get back into flow.
 */
export function WorkspaceOverviewPage() {
  const navigate = useNavigate();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [headBySpace, setHeadBySpace] = useState<Record<string, HeadState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Repo | null>(null);
  const menuContainerRef = useRef<HTMLDivElement | null>(null);

  // Close the kebab menu when clicking anywhere outside of it.
  useEffect(() => {
    if (!openMenuId) return;
    const handler = (e: MouseEvent) => {
      if (!menuContainerRef.current) return;
      if (!menuContainerRef.current.contains(e.target as Node)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [openMenuId]);

  const refreshWorkspace = async () => {
    const [s, r] = await Promise.all([getRecentSessionsGeneric(), getRepos()]);
    setSessions(s);
    setRepos(r);
    const repoIds = Array.from(
      new Set(s.map(sess => sess.repo_id).filter((id): id is string => !!id)),
    ).slice(0, 8);
    const heads = await Promise.all(
      repoIds.map(id =>
        getSpaceHead(id)
          .then(h => [id, h] as const)
          .catch(() => null),
      ),
    );
    const headMap: Record<string, HeadState> = {};
    for (const entry of heads) {
      if (entry) headMap[entry[0]] = entry[1];
    }
    setHeadBySpace(headMap);
  };

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [s, r] = await Promise.all([
          getRecentSessionsGeneric(),
          getRepos(),
        ]);
        setSessions(s);
        setRepos(r);

        // Fetch HEAD for spaces that appear in the recent sessions list.
        // This is small (typically 1-5 spaces) and runs in parallel.
        const repoIds = Array.from(
          new Set(s.map(sess => sess.repo_id).filter((id): id is string => !!id)),
        ).slice(0, 8);

        const heads = await Promise.all(
          repoIds.map(id =>
            getSpaceHead(id)
              .then(h => [id, h] as const)
              .catch(() => null),
          ),
        );
        const headMap: Record<string, HeadState> = {};
        for (const entry of heads) {
          if (entry) headMap[entry[0]] = entry[1];
        }
        setHeadBySpace(headMap);
      } catch (e: any) {
        setError(e?.message || 'Failed to load workspace');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Resume candidate: most recent session that has a repo attached AND a
  // checkpoint in that space. Sessions without checkpoints are not useful to
  // resume (there's no state to return to).
  const resumeSession = sessions.find(
    s => s.repo_id && headBySpace[s.repo_id]?.commit_id,
  );
  const resumeHead = resumeSession?.repo_id
    ? headBySpace[resumeSession.repo_id]
    : null;
  const resumeRepo = resumeSession?.repo_id
    ? repos.find(r => r.id === resumeSession.repo_id)
    : null;

  // Recent spaces: unique by repo_id, in recency order from the sessions list,
  // limited to 5. Excludes the space shown in the resume card to avoid
  // duplication.
  const recentSpaceIds = Array.from(
    new Set(
      sessions
        .map(s => s.repo_id)
        .filter((id): id is string => !!id && id !== resumeSession?.repo_id),
    ),
  ).slice(0, 5);

  const handleNewSession = () => navigate('/sessions/new');
  const handleOpenSession = (id: string) => navigate(`/sessions/${id}`);

  const formatAgo = (iso: string) => {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diff = Math.max(0, now - then);
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(iso).toLocaleDateString();
  };

  return (
    <div className="min-h-screen bg-black text-white flex flex-col">
      {/* Thin top bar */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-gray-900">
        <div className="flex items-center gap-2">
          <span
            className="text-2xl font-bold"
            style={{
              background: 'linear-gradient(135deg, #8b5cf6, #a78bfa, #c4b5fd)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            स्मृति
          </span>
          <span className="text-lg font-semibold">Smriti</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleNewSession}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-700 text-gray-300 hover:bg-zinc-800 hover:text-white transition-colors text-xs"
          >
            <Plus className="w-3.5 h-3.5" /> New session
          </button>
          <a
            href="/settings"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-800 text-gray-500 hover:text-gray-300 hover:border-gray-700 transition-colors text-xs"
          >
            <Settings2 className="w-3.5 h-3.5" /> Settings
          </a>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-6 py-10">
        <div className="max-w-3xl mx-auto space-y-10">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-gray-500 gap-3">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Loading your workspace…</span>
            </div>
          ) : error ? (
            <div className="border border-red-500/30 bg-red-500/10 text-red-300 rounded-lg p-4 text-sm">
              {error}
            </div>
          ) : sessions.length === 0 && repos.length === 0 ? (
            <EmptyState onStart={handleNewSession} />
          ) : (
            <>
              {/* Hero: Resume card */}
              {resumeSession && resumeHead && resumeRepo ? (
                <section>
                  <p className="text-[10px] uppercase tracking-widest text-gray-600 mb-3">
                    Pick up where you left off
                  </p>
                  <div
                    className="relative"
                    ref={openMenuId === resumeRepo.id ? menuContainerRef : undefined}
                  >
                  <button
                    onClick={() => handleOpenSession(resumeSession.id)}
                    className="w-full text-left border border-purple-500/30 bg-gradient-to-br from-purple-900/10 to-transparent rounded-xl p-6 hover:border-purple-500/50 hover:from-purple-900/20 transition-colors group"
                  >
                    <div className="flex items-start justify-between gap-4 mb-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1 text-[10px] uppercase tracking-wider text-gray-500">
                          <FolderOpen className="w-3 h-3" />
                          <span>{resumeRepo.name}</span>
                          <span>·</span>
                          <span>{formatAgo(resumeSession.updated_at)}</span>
                        </div>
                        <h2 className="text-lg font-semibold text-white truncate">
                          {resumeSession.title || 'Untitled session'}
                        </h2>
                      </div>
                      <div className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-purple-500/40 text-purple-200 group-hover:bg-purple-900/30 transition-colors text-xs">
                        Continue
                        <ArrowRight className="w-3.5 h-3.5" />
                      </div>
                    </div>
                    {resumeHead.objective && (
                      <div className="mt-4 border-t border-gray-800 pt-3">
                        <p className="text-[10px] uppercase tracking-wider text-gray-600 mb-1">
                          Current objective
                        </p>
                        <p className="text-sm text-gray-300 leading-relaxed">
                          {resumeHead.objective}
                        </p>
                      </div>
                    )}
                    {resumeHead.summary && (
                      <div className="mt-3">
                        <p className="text-[10px] uppercase tracking-wider text-gray-600 mb-1">
                          Last checkpoint
                        </p>
                        <p className="text-xs text-gray-400 leading-relaxed line-clamp-3">
                          {resumeHead.summary}
                        </p>
                      </div>
                    )}
                    <div className="mt-4 flex items-center gap-2 text-[10px] text-gray-600">
                      {resumeHead.commit_hash && (
                        <span className="flex items-center gap-1 font-mono text-blue-400/80">
                          <GitCommit className="w-2.5 h-2.5" />
                          {resumeHead.commit_hash.slice(0, 7)}
                        </span>
                      )}
                      {resumeSession.branch_name &&
                        resumeSession.branch_name !== 'main' && (
                          <span className="flex items-center gap-1 font-mono text-purple-400/80">
                            <GitBranch className="w-2.5 h-2.5" />
                            {resumeSession.branch_name}
                          </span>
                        )}
                    </div>
                  </button>
                    <button
                      onClick={e => {
                        e.stopPropagation();
                        setOpenMenuId(openMenuId === resumeRepo.id ? null : resumeRepo.id);
                      }}
                      className="absolute top-4 right-4 p-1.5 rounded hover:bg-zinc-800 text-gray-600 hover:text-gray-300 transition-colors"
                      title="Space actions"
                      aria-label="Space actions"
                    >
                      <MoreVertical className="w-4 h-4" />
                    </button>
                    {openMenuId === resumeRepo.id && (
                      <div className="absolute top-12 right-3 z-20 bg-zinc-950 border border-gray-800 rounded-lg shadow-xl py-1 min-w-[140px]">
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            setOpenMenuId(null);
                            setDeleteTarget(resumeRepo);
                          }}
                          className="w-full text-left px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 flex items-center gap-2 transition-colors"
                        >
                          <Trash2 className="w-3 h-3" /> Delete space
                        </button>
                      </div>
                    )}
                  </div>
                </section>
              ) : sessions.length > 0 ? (
                // Fallback: no checkpointed session to resume, but sessions exist
                <section>
                  <p className="text-[10px] uppercase tracking-widest text-gray-600 mb-3">
                    Recent session
                  </p>
                  <button
                    onClick={() => handleOpenSession(sessions[0].id)}
                    className="w-full text-left border border-gray-800 bg-zinc-900/30 rounded-xl p-5 hover:bg-zinc-900/50 hover:border-gray-700 transition-colors group"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <h2 className="text-base font-medium text-white truncate">
                          {sessions[0].title || 'Untitled session'}
                        </h2>
                        <p className="text-[10px] text-gray-600 mt-0.5">
                          {formatAgo(sessions[0].updated_at)} · no checkpoints yet
                        </p>
                      </div>
                      <ArrowRight className="w-4 h-4 text-gray-500 group-hover:text-white transition-colors flex-shrink-0 mt-1" />
                    </div>
                  </button>
                </section>
              ) : null}

              {/* Recent spaces */}
              {recentSpaceIds.length > 0 && (
                <section>
                  <p className="text-[10px] uppercase tracking-widest text-gray-600 mb-3">
                    Other recent spaces
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {recentSpaceIds.map(id => {
                      const repo = repos.find(r => r.id === id);
                      if (!repo) return null;
                      const head = headBySpace[id];
                      const latestSession = sessions.find(s => s.repo_id === id);
                      return (
                        <div
                          key={id}
                          className="relative"
                          ref={openMenuId === id ? menuContainerRef : undefined}
                        >
                          <button
                            onClick={() =>
                              latestSession
                                ? handleOpenSession(latestSession.id)
                                : handleNewSession()
                            }
                            className="w-full text-left border border-gray-800 bg-zinc-900/30 rounded-lg p-4 hover:bg-zinc-900/50 hover:border-gray-700 transition-colors"
                          >
                            <div className="flex items-center gap-2 mb-1 pr-5">
                              <FolderOpen className="w-3 h-3 text-gray-600 flex-shrink-0" />
                              <span className="text-sm text-gray-200 truncate flex-1">
                                {repo.name}
                              </span>
                            </div>
                            {head?.summary ? (
                              <p className="text-[11px] text-gray-500 leading-relaxed line-clamp-2 mt-1">
                                {head.summary}
                              </p>
                            ) : (
                              <p className="text-[11px] text-gray-700 italic mt-1">
                                No checkpoints yet
                              </p>
                            )}
                            {latestSession && (
                              <p className="text-[10px] text-gray-700 mt-2">
                                {formatAgo(latestSession.updated_at)}
                              </p>
                            )}
                          </button>
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              setOpenMenuId(openMenuId === id ? null : id);
                            }}
                            className="absolute top-3 right-3 p-1 rounded hover:bg-zinc-800 text-gray-600 hover:text-gray-300 transition-colors"
                            title="Space actions"
                            aria-label="Space actions"
                          >
                            <MoreVertical className="w-3.5 h-3.5" />
                          </button>
                          {openMenuId === id && (
                            <div className="absolute top-10 right-2 z-20 bg-zinc-950 border border-gray-800 rounded-lg shadow-xl py-1 min-w-[140px]">
                              <button
                                onClick={e => {
                                  e.stopPropagation();
                                  setOpenMenuId(null);
                                  setDeleteTarget(repo);
                                }}
                                className="w-full text-left px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 flex items-center gap-2 transition-colors"
                              >
                                <Trash2 className="w-3 h-3" /> Delete space
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {/* Quick actions */}
              <section className="pt-4 border-t border-gray-900">
                <div className="flex items-center gap-3 flex-wrap">
                  <button
                    onClick={handleNewSession}
                    className="flex items-center gap-2 px-4 py-2 rounded-md border border-gray-700 text-gray-300 hover:bg-zinc-900 hover:text-white transition-colors text-sm"
                  >
                    <MessageSquare className="w-4 h-4" /> Start a new session
                  </button>
                  {sessions.length > 0 && (
                    <span className="text-[11px] text-gray-600">
                      {sessions.length} session{sessions.length === 1 ? '' : 's'} across{' '}
                      {repos.length} space{repos.length === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
              </section>
            </>
          )}
        </div>
      </main>

      {deleteTarget && (
        <ConfirmDeleteModal
          title={`Delete space '${deleteTarget.name}'?`}
          body="This will permanently delete the space, all of its checkpoints, sessions, and turns. This cannot be undone."
          onClose={() => setDeleteTarget(null)}
          onConfirm={async () => {
            await deleteRepo(deleteTarget.id);
            setDeleteTarget(null);
            await refreshWorkspace();
          }}
        />
      )}
    </div>
  );
}

function EmptyState({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-20 space-y-6">
      <div className="w-14 h-14 rounded-xl border border-gray-800 bg-zinc-900/50 flex items-center justify-center">
        <RotateCcw className="w-6 h-6 text-gray-600" />
      </div>
      <div className="space-y-2">
        <h2 className="text-xl font-semibold text-white">Welcome to Smriti</h2>
        <p className="text-sm text-gray-400 max-w-md">
          A workspace for reasoning state. Start a session, checkpoint your thinking,
          and come back without losing where you were.
        </p>
      </div>
      <button
        onClick={onStart}
        className="flex items-center gap-2 px-5 py-2.5 rounded-md bg-white text-black hover:bg-gray-200 transition-colors text-sm font-medium"
      >
        <Plus className="w-4 h-4" /> Start your first session
      </button>
    </div>
  );
}
