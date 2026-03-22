import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { extractMemories } from '../api/client';
import { ArrowLeft, DatabaseBackup, Info } from 'lucide-react';

export function IngestPage() {
  const navigate = useNavigate();
  const [transcript, setTranscript] = useState('');
  const [title, setTitle] = useState('');
  const [sourceTool, setSourceTool] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!transcript.trim()) {
      setError('Please paste a transcript.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      await extractMemories(transcript);
      navigate(`/`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8 animate-fade-in relative pt-4">
      <button onClick={() => navigate('/')} className="flex items-center gap-2 text-gray-500 hover:text-white transition-colors text-sm">
        <ArrowLeft className="w-4 h-4" /> Back to Repos
      </button>

      {/* Hero */}
      <div className="border-b border-gray-800 pb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2 text-gray-300">
          <DatabaseBackup className="w-5 h-5" />
          Legacy Transcript Backfill
        </h1>
        <p className="text-gray-500 mt-2 text-sm leading-relaxed">
          The preferred way to use Smriti is for agents to push Commits directly using the REST API. 
          Use this utility solely to bootstrap a memory space from older chat logs.
        </p>
      </div>

      <div className="bg-blue-900/10 border border-blue-900/30 rounded-lg p-4 flex gap-3 text-sm text-blue-400">
        <Info className="w-5 h-5 flex-shrink-0 mt-0.5" />
        <p>Imported memories will be processed asynchronously and deposited into the legacy tables. They will not immediately mirror into the Repo/Commit timeline.</p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Title & Source Tool */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="title" className="block text-xs font-medium mb-1.5 text-gray-400 uppercase tracking-wider">
              Session title
            </label>
            <input
              id="title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Database refactoring"
              className="input-field"
              disabled={loading}
            />
          </div>
          <div>
            <label htmlFor="source-tool" className="block text-xs font-medium mb-1.5 text-gray-400 uppercase tracking-wider">
              Source tool
            </label>
            <select
              id="source-tool"
              value={sourceTool}
              onChange={(e) => setSourceTool(e.target.value)}
              className="input-field"
              disabled={loading}
            >
              <option value="">Auto-detect</option>
              <option value="chatgpt">ChatGPT</option>
              <option value="claude">Claude</option>
              <option value="cursor">Cursor</option>
              <option value="other">Other</option>
            </select>
          </div>
        </div>

        {/* Transcript textarea */}
        <div>
          <label htmlFor="transcript" className="block text-xs font-medium mb-1.5 text-gray-400 uppercase tracking-wider">
            Raw Transcript
          </label>
          <textarea
            id="transcript"
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder={'Human: Can you help me refactor the auth module?\n\nAssistant: Sure!...'}
            rows={10}
            className="w-full px-4 py-3 rounded-md text-sm font-mono outline-none resize-y bg-gray-900/50 border border-gray-800 text-gray-300 focus:border-gray-500"
            disabled={loading}
          />
          <p className="text-[11px] mt-1.5 text-gray-500 float-right">
            {transcript.length > 0
              ? `${transcript.split(/\s+/).filter(Boolean).length} words`
              : 'Supports common parser formats'}
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded-md text-sm text-center">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading || !transcript.trim()}
          className="w-full bg-gray-800 hover:bg-gray-700 text-white font-medium py-3 rounded-md transition-colors border border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed mt-4"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity="0.25" />
                <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" opacity="0.75" />
              </svg>
              Processing Legacy Import...
            </span>
          ) : (
            'Extract & Backfill'
          )}
        </button>
      </form>
    </div>
  );
}
