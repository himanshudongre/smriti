import { useEffect, useState } from 'react';
import { getProviderStatus } from '../api/client';
import type { ProviderStatus } from '../types';
import { CheckCircle, XCircle, AlertCircle } from 'lucide-react';

const PROVIDERS: { id: string; label: string; envVar: string }[] = [
  { id: 'openai', label: 'OpenAI', envVar: 'OPENAI_API_KEY' },
  { id: 'anthropic', label: 'Anthropic', envVar: 'ANTHROPIC_API_KEY' },
  { id: 'openrouter', label: 'OpenRouter', envVar: 'OPENROUTER_API_KEY' },
];

export function SettingsPage() {
  const [status, setStatus] = useState<Record<string, ProviderStatus> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProviderStatus().then(setStatus).catch(e => setError(e.message));
  }, []);

  return (
    <div className="max-w-2xl mx-auto space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-gray-500 text-sm mt-1">
          Provider configuration status. To enable a provider, add the API key to{' '}
          <code className="text-gray-400">config/providers.yaml</code> or set the environment variable.
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      <div className="card divide-y divide-gray-800">
        {PROVIDERS.map(({ id, label, envVar }) => {
          const s = status?.[id];
          return (
            <div key={id} className="flex items-center justify-between py-4 first:pt-0 last:pb-0">
              <div>
                <p className="font-medium text-white">{label}</p>
                <code className="text-xs text-gray-600 mt-0.5">{envVar}</code>
              </div>
              <div className="flex items-center gap-2">
                {!s ? (
                  <span className="text-gray-600 text-xs">Loading…</span>
                ) : s.missing_package ? (
                  <span className="flex items-center gap-1.5 text-yellow-500 text-sm">
                    <AlertCircle className="w-4 h-4" /> Package not installed
                  </span>
                ) : !s.has_key ? (
                  <span className="flex items-center gap-1.5 text-gray-500 text-sm">
                    <XCircle className="w-4 h-4" /> No API key
                  </span>
                ) : !s.enabled ? (
                  <span className="flex items-center gap-1.5 text-gray-500 text-sm">
                    <XCircle className="w-4 h-4" /> Disabled
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-green-400 text-sm">
                    <CheckCircle className="w-4 h-4" /> Configured and ready
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div>
        <h2 className="text-xl font-bold text-white mb-4">Background Intelligence</h2>
        <div className="card border-gray-800 p-5 bg-zinc-900/40">
          <p className="text-sm text-gray-400 mb-4">
            This provider and model are used for invisible background tasks like Auto Checkpoint Drafting.
            Configure this in <code>config/providers.yaml</code>.
          </p>
          <div className="flex items-center gap-12">
            <div>
              <p className="text-xs uppercase tracking-wider text-gray-600 mb-1">Provider</p>
              <p className="font-medium text-white capitalize">{status?.['background_intelligence']?.provider || 'Loading...'}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-gray-600 mb-1">Model</p>
              <p className="font-medium text-white">{status?.['background_intelligence']?.model || 'Loading...'}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="card bg-zinc-900/40 border-gray-800">
        <p className="text-xs text-gray-500 leading-relaxed">
          <strong className="text-gray-400">Using Smriti with real models:</strong> Copy{' '}
          <code>backend/config/providers.example.yaml</code> to{' '}
          <code>backend/config/providers.yaml</code>, fill in your API keys, and restart the backend.
          Alternatively, set the environment variable directly in your shell before running{' '}
          <code>uvicorn</code>. The chat workspace shows a <strong>Use mock</strong> toggle for
          offline demos that requires no keys.
        </p>
      </div>
    </div>
  );
}
