import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { IngestPage } from './pages/IngestPage';
import { HomePage } from './pages/HomePage';
import { RepoDetailPage } from './pages/RepoDetailPage';
import { CommitDetailPage } from './pages/CommitDetailPage';
import { ChatWorkspacePage } from './pages/ChatWorkspacePage';
import { LineagePage } from './pages/LineagePage';
import { SettingsPage } from './pages/SettingsPage';
import { WorkspaceOverviewPage } from './pages/WorkspaceOverviewPage';
import './App.css';

function App() {
  return (
    <Router>
      <Routes>
        {/* Resume-focused landing page */}
        <Route path="/" element={<WorkspaceOverviewPage />} />

        {/* Chat workspace — full-screen, own layout */}
        <Route path="/sessions/new" element={<ChatWorkspacePage />} />
        <Route path="/sessions/:sessionId" element={<ChatWorkspacePage />} />

        {/* Branch/lineage tree — full-screen, own layout */}
        <Route path="/spaces/:spaceId/lineage" element={<LineagePage />} />

        {/* Shell-wrapped legacy / debug routes */}
        <Route path="/*" element={<ShellLayout />} />
      </Routes>
    </Router>
  );
}

function ShellLayout() {
  return (
    <div className="min-h-screen" style={{ background: 'var(--color-bg)' }}>
      {/* Header */}
      <header
        className="sticky top-0 z-50 border-b"
        style={{
          background: 'rgba(9, 9, 11, 0.9)',
          backdropFilter: 'blur(12px)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2 no-underline">
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
            <span className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>
              Smriti
            </span>
          </a>
          <div className="flex items-center gap-4">
            <a
              href="/settings"
              className="text-sm no-underline"
              style={{ color: 'var(--color-text-dim)' }}
            >
              Settings
            </a>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-5xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/debug" element={<HomePage />} />
          <Route path="/repos/:id" element={<RepoDetailPage />} />
          <Route path="/commits/:id" element={<CommitDetailPage />} />
          <Route path="/import" element={<IngestPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
