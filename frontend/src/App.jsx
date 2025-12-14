import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Operations from './pages/Operations';
import History from './pages/History';
import Logs from './pages/Logs';
import DraftingWorkLoad from './pages/DraftingWorkLoad';
import JobLog from './pages/JobLog';
import Navbar from './components/Navbar';
import './App.css';

function AppContent() {
  const location = useLocation();
  const showNavbar = location.pathname !== '/drafting-work-load';

  return (
    <div className="w-full min-h-screen" style={{ width: '100%', minWidth: '100%' }}>
      {showNavbar && <Navbar />}
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/operations" element={<Operations />} />
        <Route path="/history" element={<History />} />
        <Route path="/drafting-work-load" element={<DraftingWorkLoad />} />
        <Route path="/jobs" element={<JobLog />} />
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