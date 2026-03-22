import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getRepos, createRepo } from '../api/client';
import type { Repo } from '../types';
import { FolderGit2, MessageSquare, Plus, AlertTriangle, GitCommitHorizontal } from 'lucide-react';

export function HomePage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Create state
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const navigate = useNavigate();

  const fetchRepos = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getRepos();
      setRepos(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load Repos. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRepos();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      setCreating(true);
      setError(null);
      
      // Implement an 8-second timeout to catch silent hung SQLite locks
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Backend unreachable or database locked. Please verify uvicorn is running.')), 8000)
      );
      
      const r = await Promise.race([
        createRepo({ name: newName, description: newDesc }),
        timeoutPromise
      ]) as Repo;
      
      navigate(`/repos/${r.id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to create repo');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded-md flex items-center gap-2 mb-6">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-gray-800 pb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white">Repo Spaces</h1>
          <p className="text-gray-400 mt-1 text-sm">Shared, versioned workspaces for cross-agent memory</p>
        </div>
        <a 
            href="/import"
            className="text-xs text-gray-400 hover:text-white transition-colors cursor-pointer border border-gray-800 hover:border-gray-600 px-3 py-1.5 rounded"
        >
          Legacy Transcript Backfill
        </a>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Create Card */}
        <div className="card border-dashed border-2 bg-transparent hover:bg-gray-900/30 transition-colors">
          <form onSubmit={handleCreate} className="h-full flex flex-col justify-center space-y-4">
            <h3 className="font-semibold text-lg flex items-center gap-2 mb-2">
              <Plus className="w-5 h-5 text-gray-400" />
              New Space
            </h3>
            <input
              type="text"
              placeholder="e.g. Auth Migration"
              className="input-field"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              disabled={creating}
              required
            />
            <input
              type="text"
              placeholder="Description (optional)"
              className="input-field text-sm"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              disabled={creating}
            />
            <button type="submit" className="button-primary w-full mt-2" disabled={creating || !newName.trim()}>
              {creating ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity="0.25" />
                    <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" opacity="0.75" />
                  </svg>
                  Creating...
                </span>
              ) : 'Create Repo'}
            </button>
          </form>
        </div>

        {loading && (
          <div className="col-span-2 flex flex-col items-center justify-center p-12 text-gray-500 space-y-4">
             <svg className="animate-spin h-8 w-8" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity="0.25" />
                <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" opacity="0.75" />
             </svg>
             <p className="text-sm">Connecting to backend...</p>
          </div>
        )}

        {!loading && repos.length === 0 && !error && (
          <div className="col-span-2 flex items-center justify-center p-12 border border-dashed border-gray-800 rounded-lg">
            <p className="text-gray-500 text-sm">No Repositories found. Create one to begin.</p>
          </div>
        )}

        {!loading && repos.map((r) => (
          <div key={r.id} className="card flex flex-col justify-between">
            <div>
              <div className="flex items-start justify-between">
                <FolderGit2 className="w-5 h-5 text-gray-400" />
                <span className="font-mono text-[10px] text-gray-600 border border-gray-800 px-1.5 py-0.5 rounded">
                  {r.id.substring(0, 8)}
                </span>
              </div>
              <h3 className="text-lg font-bold mt-4 mb-1 truncate text-white">{r.name}</h3>
              <p className="text-gray-500 text-sm line-clamp-2 min-h-8">
                {r.description || 'No description.'}
              </p>
            </div>

            <div className="mt-5 pt-4 border-t border-gray-800 space-y-2">
              {/* Primary: open chat */}
              <button
                onClick={() => navigate(`/spaces/${r.id}/chat`)}
                className="w-full flex items-center justify-center gap-2 button-primary py-2 text-sm"
              >
                <MessageSquare className="w-3.5 h-3.5" /> Open Chat
              </button>
              {/* Secondary: browse commits */}
              <button
                onClick={() => navigate(`/repos/${r.id}`)}
                className="w-full flex items-center justify-center gap-2 py-1.5 text-xs text-gray-600 hover:text-gray-300 transition-colors"
              >
                <GitCommitHorizontal className="w-3.5 h-3.5" /> Commit history
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
