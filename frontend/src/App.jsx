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
import Archive from './pages/Archive';
import PMBoardContent from './pages/PMBoardContent';
import Login from './pages/Login';
import JobsiteMap from './pages/maps/JobsiteMap';
import Board from './pages/Board';
import Meetings from './pages/Meetings';
import ToDos from './pages/ToDos';
import TMTickets from './pages/TMTickets';
import SubcontractorAdmin from './pages/SubcontractorAdmin';
import FcCollection from './pages/FcCollection';
import InvoicingReport from './pages/InvoicingReport';
import RentalReports from './pages/RentalReports';
import SubcontractorShell from './components/SubcontractorShell';
import SubcontractorAcceptInvite from './pages/SubcontractorAcceptInvite';
import SubcontractorTicketList from './pages/SubcontractorTicketList';
import SubcontractorTicketDetail from './pages/SubcontractorTicketDetail';
import { checkAuth } from './utils/auth';
import { checkSubcontractorAuth } from './utils/subcontractorAuth';
import './App.css';

function AppContent() {
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const [subcontractor, setSubcontractor] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    verifyAuth();
  }, []);

  const verifyAuth = async () => {
    const user = await checkAuth();
    setIsAuthenticated(!!user);
    // Only relevant when NOT a staff session — a subcontractor who wanders into
    // the staff area (e.g. an old bookmark, a mistyped URL) gets a tailored
    // message pointing them back to /sub/tickets instead of a generic "log in".
    if (!user) {
      setSubcontractor(await checkSubcontractorAuth());
    }
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
        {/* Subcontractor routes (other than /sub/login, which renders the SAME Login page
            with its Subcontractor tab preselected) are a SEPARATE top-level tree, not nested
            under AppShell: AppShell's auth check is keyed to the internal-staff session
            (isAuthenticated above, driven by /api/auth/me) and would 401-and-bounce a logged-in
            subcontractor. SubcontractorShell does its own session check instead. */}
        <Route path="/sub/login" element={<Login onLogin={verifyAuth} />} />
        <Route path="/sub/accept-invite/:token" element={<SubcontractorAcceptInvite />} />
        <Route path="/sub" element={<SubcontractorShell />}>
          <Route path="tickets" element={<SubcontractorTicketList />} />
          <Route path="tickets/:id" element={<SubcontractorTicketDetail />} />
        </Route>
        <Route path="/" element={<AppShell isAuthenticated={isAuthenticated} subcontractor={subcontractor} />}>
          {isAuthenticated ? (
            <>
              <Route index element={<Navigate to="/job-log" replace />} />
              {/* Shared releases shell: the toolbar/header stays mounted across
                  Table ↔ Board ↔ Timeline; only the Outlet content swaps. */}
              <Route element={<ReleasesLayout />}>
                <Route path="job-log" element={<JobLogContent />} />
                <Route path="pm-board" element={<PMBoardContent />} />
              </Route>
              <Route path="archive" element={<Archive />} />
              <Route path="events" element={<Events />} />
              <Route path="drafting-work-load" element={<DraftingWorkLoad />} />
              <Route path="drafting-work-load/admin" element={<DraftingWorkLoadAdmin />} />
              <Route path="jobsite-map" element={<JobsiteMap />} />
              <Route path="board" element={<Board />} />
              <Route path="meetings" element={<Meetings />} />
              <Route path="todos" element={<ToDos />} />
              <Route path="tm-tickets" element={<TMTickets />} />
              <Route path="subcontractors" element={<SubcontractorAdmin />} />
              <Route path="invoicing-report" element={<InvoicingReport />} />
              <Route path="rental-reports" element={<RentalReports />} />
              <Route path="admin/fc-collection" element={<FcCollection />} />
              <Route path="*" element={<Navigate to="/job-log" replace />} />
            </>
          ) : (
            <Route path="*" element={<LoginPrompt subcontractor={subcontractor} />} />
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
