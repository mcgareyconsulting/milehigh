import { useNavigate, useLocation } from 'react-router-dom';

function Navbar() {
    const navigate = useNavigate();
    const location = useLocation();

    const isActive = (path) => location.pathname === path;

    return (
        <nav className="w-full bg-white/95 backdrop-blur-sm shadow-lg border-b border-gray-200 sticky top-0 z-50" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-7xl mx-auto px-6 py-4 w-full" style={{ width: '100%', maxWidth: '1280px' }}>
                <div className="flex items-center justify-between">
                    <div
                        className="text-2xl font-bold bg-gradient-to-r from-accent-500 to-accent-600 bg-clip-text text-transparent cursor-pointer hover:from-accent-600 hover:to-accent-700 transition-all"
                        onClick={() => navigate('/')}
                    >
                        Mile High Metal Works Dashboard
                    </div>
                    <div className="flex gap-4">
                        <button
                            onClick={() => navigate('/operations')}
                            className={`px-6 py-2 rounded-lg font-medium transition-all duration-200 ${isActive('/operations')
                                ? 'bg-accent-500 text-white shadow-md'
                                : 'text-gray-700 hover:bg-gray-100'
                                }`}
                        >
                            Operations
                        </button>
                        <button
                            onClick={() => navigate('/history')}
                            className={`px-6 py-2 rounded-lg font-medium transition-all duration-200 ${isActive('/history')
                                ? 'bg-accent-500 text-white shadow-md'
                                : 'text-gray-700 hover:bg-gray-100'
                                }`}
                        >
                            History
                        </button>
                        <button
                            onClick={() => navigate('/')}
                            className={`px-6 py-2 rounded-lg font-medium transition-all duration-200 ${isActive('/')
                                ? 'bg-accent-500 text-white shadow-md'
                                : 'text-gray-700 hover:bg-gray-100'
                                }`}
                        >
                            Dashboard
                        </button>
                    </div>
                </div>
            </div>
        </nav>
    );
}

export default Navbar;

