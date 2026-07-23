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
import UpdateAvailableBanner from './components/UpdateAvailableBanner';
import DraftingWorkLoad from './pages/DraftingWorkLoad';
import DraftingWorkLoadAdmin from './pages/DraftingWorkLoadAdmin';
import Events from './pages/Events';
import ReleasesLayout from './pages/ReleasesLayout';
import JobLogContent from './pages/JobLogContent';
import Projects from './pages/Projects';
import ProjectDetail from './pages/ProjectDetail';
import GridDemo from './pages/GridDemo'; // TEMPORARY: K2 grid harness, remove when D1 ships
import Archive from './pages/Archive';
import PMBoardContent from './pages/PMBoardContent';
import Login from './pages/Login';
import JobsiteMap from './pages/maps/JobsiteMap';
import Board from './pages/Board';
import Meetings from './pages/Meetings';
import ToDos from './pages/ToDos';
import FcCollection from './pages/FcCollection';
import SubmittalMatching from './pages/SubmittalMatching';
import InvoicingReport from './pages/InvoicingReport';
import RentalReports from './pages/RentalReports';
import Metrics from './pages/Metrics';
import InstallSchedule from './pages/InstallSchedule';
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
    <>
      <UpdateAvailableBanner />
      <Routes>
        <Route path="/login" element={<Login onLogin={verifyAuth} />} />
        <Route path="/" element={<AppShell isAuthenticated={isAuthenticated} />}>
          {isAuthenticated ? (
            <>
              <Route index element={<Navigate to="/job-log" replace />} />
              {/* Shared releases shell: the toolbar/header stays mounted across
                  Table ↔ Board ↔ Timeline; only the Outlet content swaps. */}
              <Route element={<ReleasesLayout />}>
                <Route path="job-log" element={<JobLogContent />} />
                <Route path="pm-board" element={<PMBoardContent />} />
              </Route>
              <Route path="projects" element={<Projects />} />
              <Route path="projects/:id" element={<ProjectDetail />} />
              {/* TEMPORARY: K2 grid engine harness. Delete with GridDemo.jsx once D1 ships. */}
              <Route path="grid-demo" element={<GridDemo />} />
              <Route path="archive" element={<Archive />} />
              <Route path="events" element={<Events />} />
              <Route path="drafting-work-load" element={<DraftingWorkLoad />} />
              <Route path="drafting-work-load/admin" element={<DraftingWorkLoadAdmin />} />
              <Route path="jobsite-map" element={<JobsiteMap />} />
              <Route path="board" element={<Board />} />
              <Route path="meetings" element={<Meetings />} />
              <Route path="todos" element={<ToDos />} />
              <Route path="install-schedule" element={<InstallSchedule />} />
              <Route path="invoicing-report" element={<InvoicingReport />} />
              <Route path="rental-reports" element={<RentalReports />} />
              <Route path="admin/fc-collection" element={<FcCollection />} />
              <Route path="admin/submittal-matching" element={<SubmittalMatching />} />
              <Route path="admin/metrics" element={<Metrics />} />
              <Route path="*" element={<Navigate to="/job-log" replace />} />
            </>
          ) : (
            <Route path="*" element={<LoginPrompt />} />
          )}
        </Route>
      </Routes>
    </>
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
