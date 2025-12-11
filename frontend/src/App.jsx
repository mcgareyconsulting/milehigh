import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Operations from './pages/Operations';
import History from './pages/History';
import Logs from './pages/Logs';
import DraftingWorkLoad from './pages/DraftingWorkLoad';
import Jobs from './pages/Jobs';
import Navbar from './components/Navbar';
import './App.css';

function App() {
  return (
    <Router>
      <div className="w-full min-h-screen" style={{ width: '100%', minWidth: '100%' }}>
        <Navbar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/operations" element={<Operations />} />
          <Route path="/history" element={<History />} />
          <Route path="/drafting-work-load" element={<DraftingWorkLoad />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/operations/:operationId/logs" element={<Logs />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;