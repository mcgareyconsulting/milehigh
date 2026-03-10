import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import AppShell from './components/AppShell';
import LoginPrompt from './components/LoginPrompt';
import DraftingWorkLoad from './pages/DraftingWorkLoad';
import DraftingWorkLoadAdmin from './pages/DraftingWorkLoadAdmin';
import Events from './pages/Events';
import JobLog from './pages/JobLog';
import Login from './pages/Login';
import { checkAuth } from './utils/auth';
import { ThemeProvider } from './context/ThemeContext';
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
            <Route path="events" element={<Events />} />
            <Route path="drafting-work-load" element={<DraftingWorkLoad />} />
            <Route path="drafting-work-load/admin" element={<DraftingWorkLoadAdmin />} />
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
    <ThemeProvider>
      <Router>
        <AppContent />
      </Router>
    </ThemeProvider>
  );
}

export default App;
