import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Operations from './pages/Operations';
import History from './pages/History';
import Events from './pages/Events';
import Logs from './pages/Logs';
import DraftingWorkLoad from './pages/DraftingWorkLoad';
import DraftingWorkLoadAdmin from './pages/DraftingWorkLoadAdmin';
import JobLog from './pages/JobLog';
import Navbar from './components/Navbar';
import './App.css';

function AppContent() {
  const location = useLocation();
  const showNavbar = location.pathname !== '/drafting-work-load' && location.pathname !== '/drafting-work-load/admin';

  return (
    <div className="w-full min-h-screen" style={{ width: '100%', minWidth: '100%' }}>
      {showNavbar && <Navbar />}
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/operations" element={<Operations />} />
        <Route path="/history" element={<History />} />
        <Route path="/events" element={<Events />} />
        <Route path="/drafting-work-load" element={<DraftingWorkLoad />} />
        <Route path="/drafting-work-load/admin" element={<DraftingWorkLoadAdmin />} />
        <Route path="/job-log" element={<JobLog />} />
        <Route path="/operations/:operationId/logs" element={<Logs />} />
      </Routes>
    </div>
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