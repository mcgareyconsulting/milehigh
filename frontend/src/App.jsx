/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Top-level route configuration that gates all pages behind session authentication and redirects unauthenticated users to a login prompt.
 * exports:
 *   App: Root component wrapping BrowserRouter, auth check, and all page routes
 * imports_from: [react-router-dom, react, ./components/AppShell, ./components/LoginPrompt, ./pages/DraftingWorkLoad, ./pages/DraftingWorkLoadAdmin, ./pages/Events, ./pages/JobLog]
 * imported_by: [main.jsx]
 * invariants:
 *   - Authenticated users default-redirect to /job-log; unauthenticated users see LoginPrompt on any route
 *   - Auth state is checked once on mount via checkAuth; child pages may re-check independently
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import AppShell from './components/AppShell';
import LoginPrompt from './components/LoginPrompt';
import DraftingWorkLoad from './pages/DraftingWorkLoad';
import DraftingWorkLoadAdmin from './pages/DraftingWorkLoadAdmin';
import Events from './pages/Events';
import JobLog from './pages/JobLog';
import Archive from './pages/Archive';
import PMBoard from './pages/PMBoard';
import Login from './pages/Login';
import JobsiteMap from './pages/maps/JobsiteMap';
import Board from './pages/Board';
import AdminMicrosoft from './pages/AdminMicrosoft';
import { checkAuth } from './utils/auth';
import './App.css';

function AppContent() {
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    verifyAuth();
  }, []);

  const verifyAuth = async () => {
    const user = await checkAuth();
    setIsAuthenticated(!!user);
    setLoading(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] dark:bg-slate-900">
        <div className="text-gray-600 dark:text-slate-400">Loading...</div>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<Login onLogin={verifyAuth} />} />
      <Route path="/" element={<AppShell isAuthenticated={isAuthenticated} />}>
        {isAuthenticated ? (
          <>
            <Route index element={<Navigate to="/job-log" replace />} />
            <Route path="job-log" element={<JobLog />} />
            <Route path="archive" element={<Archive />} />
            <Route path="events" element={<Events />} />
            <Route path="drafting-work-load" element={<DraftingWorkLoad />} />
            <Route path="drafting-work-load/admin" element={<DraftingWorkLoadAdmin />} />
            <Route path="pm-board" element={<PMBoard />} />
            <Route path="jobsite-map" element={<JobsiteMap />} />
            <Route path="board" element={<Board />} />
            <Route path="admin/microsoft" element={<AdminMicrosoft />} />
            <Route path="*" element={<Navigate to="/job-log" replace />} />
          </>
        ) : (
          <Route path="*" element={<LoginPrompt />} />
        )}
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;
