import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getRepo, getRepoCommits } from '../api/client';
import type { Repo, Commit } from '../types';
import {
  GitCommit,
  GitBranch,
  ArrowLeft,
  Plus,
  AlertTriangle,
  PlayCircle,
  GitCommitHorizontal,
  Clock,
} from 'lucide-react';
import { CreateCommitPanel } from '../components/CreateCommitPanel';

export function RepoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [repo, setRepo] = useState<Repo | null>(null);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPanel, setShowPanel] = useState(false);

  const fetchData = async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const timeout = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Backend unreachable. Is uvicorn running on 127.0.0.1:8000?')), 8000),
      );
      const [r, c] = await Promise.race([
        Promise.all([getRepo(id), getRepoCommits(id)]),
        timeout,
      ]) as [Repo, Commit[]];
      setRepo(r);
      setCommits(c);
    } catch (err: any) {
      setError(err.message || 'Failed to load repo');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [id]);

  const handleCommitCreated = (commit: Commit) => {
    setShowPanel(false);
    // Optimistically prepend to timeline, then re-fetch for accuracy
    setCommits(prev => [commit, ...prev]);
    fetchData();
  };

  const handleContinueFromLatest = async () => {
    if (!id || commits.length === 0) return;
    navigate(`/commits/${commits[0].id}`);
  };

  // ── Loading ───────────────────────────────────────────────────────────────
  if (loading) return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-500 space-y-4">
      <svg className="animate-spin h-8 w-8" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity="0.25" />
        <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" opacity="0.75" />
      </svg>
      <p className="text-sm">Loading workspace…</p>
    </div>
  );

  if (!repo && !error) return <div className="text-red-500 py-10">Not Found</div>;

  const latestCommit = commits[0] ?? null;

  return (
    <>
      {/* Create Commit slide-in panel */}
      {showPanel && id && (
        <CreateCommitPanel
          repoId={id}
          parentCommitId={latestCommit?.id ?? null}
          onClose={() => setShowPanel(false)}
          onCreated={handleCommitCreated}
        />
      )}

      <div className="space-y-8 animate-fade-in max-w-4xl mx-auto">
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm">{error}</p>
          </div>
        )}

        {/* Back */}
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Repos
        </button>

        {/* Repo header */}
        {repo && (
          <div className="card">
            <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-white tracking-tight">{repo.name}</h1>
                {repo.description && (
                  <p className="text-gray-400 mt-1 text-sm">{repo.description}</p>
                )}
                <div className="flex gap-3 mt-3 text-xs text-gray-500">
                  <span className="flex items-center gap-1 border border-gray-800 px-2 py-0.5 rounded">
                    <GitBranch className="w-3 h-3" /> main
                  </span>
                  <span className="flex items-center gap-1 border border-gray-800 px-2 py-0.5 rounded">
                    <GitCommitHorizontal className="w-3 h-3" /> {commits.length} commit{commits.length !== 1 ? 's' : ''}
                  </span>
                </div>
              </div>

              {/* CTAs */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {latestCommit ? (
                  <>
                    {/* Primary: continue from latest */}
                    <button
                      onClick={handleContinueFromLatest}
                      className="button-primary flex items-center gap-2 px-4 py-2.5"
                    >
                      <PlayCircle className="w-4 h-4" />
                      Continue from latest
                    </button>
                    {/* Secondary: new commit */}
                    <button
                      onClick={() => setShowPanel(true)}
                      className="flex items-center gap-2 px-4 py-2.5 rounded border border-gray-700 hover:bg-gray-800 text-gray-300 text-sm transition-colors"
                    >
                      <Plus className="w-4 h-4" /> New Commit
                    </button>
                  </>
                ) : (
                  /* No commits yet — single CTA */
                  <button
                    onClick={() => setShowPanel(true)}
                    className="button-primary flex items-center gap-2 px-4 py-2.5"
                  >
                    <Plus className="w-4 h-4" /> Create First Commit
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Commit timeline or empty state ───────────────────────── */}
        {commits.length === 0 ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center py-20 border border-dashed border-gray-800 rounded-lg space-y-4 text-center">
            <GitCommit className="w-10 h-10 text-gray-700" />
            <h2 className="text-white font-semibold text-lg">No commits yet</h2>
            <p className="text-gray-500 text-sm max-w-xs leading-relaxed">
              Create the first commit to start tracking your agent's state. Each commit is a structured snapshot that lets you resume anywhere.
            </p>
            <button
              onClick={() => setShowPanel(true)}
              className="mt-2 button-primary flex items-center gap-2 px-5 py-2.5"
            >
              <Plus className="w-4 h-4" /> Create First Commit
            </button>
          </div>
        ) : (
          /* Timeline */
          <div>
            <h2 className="text-sm font-medium uppercase tracking-wider text-gray-500 mb-6 flex items-center gap-2">
              <GitCommit className="w-4 h-4" /> Commit History
            </h2>
            <div className="relative border-l-2 border-gray-800 ml-4 pl-6 space-y-6">
              {commits.map((c, idx) => (
                <div
                  key={c.id}
                  className="relative group cursor-pointer"
                  onClick={() => navigate(`/commits/${c.id}`)}
                >
                  {/* Timeline dot: larger and filled for the latest */}
                  <div
                    className={`absolute -left-[33px] w-4 h-4 rounded-full border-2 transition-transform group-hover:scale-125
                      ${idx === 0
                        ? 'bg-white border-white'
                        : 'bg-gray-900 border-gray-600'}`}
                  />

                  <div className="card p-4 group-hover:border-gray-500 transition-colors">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-white truncate">{c.message}</p>
                        {c.objective && (
                          <p className="text-gray-400 text-sm mt-1 line-clamp-1">
                            Objective: {c.objective}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {idx === 0 && (
                          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-white text-black">
                            HEAD
                          </span>
                        )}
                        <span className="font-mono text-[11px] text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20">
                          {c.commit_hash.slice(0, 7)}
                        </span>
                      </div>
                    </div>

                    <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
                      {c.author_agent && (
                        <span className="border border-gray-700 font-mono px-2 py-0.5 rounded capitalize">
                          {c.author_agent}
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(c.created_at).toLocaleString()}
                      </span>
                      {c.tasks?.length > 0 && (
                        <span className="text-gray-600">{c.tasks.length} task{c.tasks.length !== 1 ? 's' : ''}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
