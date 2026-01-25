import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import Dashboard from './pages/Dashboard';
import Operations from './pages/Operations';
import History from './pages/History';
import Events from './pages/Events';
import Logs from './pages/Logs';
import DraftingWorkLoad from './pages/DraftingWorkLoad';
import DraftingWorkLoadAdmin from './pages/DraftingWorkLoadAdmin';
import JobLog from './pages/JobLog';
import PMBoard from './pages/PMBoard';
import Login from './pages/Login';
import Navbar from './components/Navbar';
import { checkAuth } from './utils/auth';
import './App.css';

function AppContent() {
  const location = useLocation();
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

  // Show loading state while checking auth
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600">Loading...</div>
      </div>
    );
  }

  // Show login page if not authenticated (except for login route itself)
  if (!isAuthenticated && location.pathname !== '/login') {
    return <Login onLogin={verifyAuth} />;
  }

  const showNavbar = location.pathname !== '/drafting-work-load' && 
                     location.pathname !== '/drafting-work-load/admin' && 
                     location.pathname !== '/job-log' &&
                     location.pathname !== '/pm-board' &&
                     location.pathname !== '/login';

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
        <Route path="/pm-board" element={<PMBoard />} />
        <Route path="/operations/:operationId/logs" element={<Logs />} />
        <Route path="/login" element={<Login onLogin={verifyAuth} />} />
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