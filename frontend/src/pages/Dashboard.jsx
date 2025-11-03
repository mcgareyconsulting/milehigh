import { useNavigate } from 'react-router-dom';

function Dashboard() {
    const navigate = useNavigate();

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-500 to-purple-600">
            <div className="bg-white p-12 rounded-xl shadow-2xl text-center max-w-md w-[90%]">
                <h1 className="text-3xl font-bold text-gray-800 mb-8">
                    Sync Operations Dashboard
                </h1>
                <div className="flex flex-col gap-4">
                    <button
                        className="px-8 py-4 bg-indigo-500 hover:bg-indigo-600 text-white font-semibold rounded-lg transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg"
                        onClick={() => navigate('/operations')}
                    >
                        Operations
                    </button>
                    <button
                        className="px-8 py-4 bg-purple-600 hover:bg-purple-700 text-white font-semibold rounded-lg transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg"
                        onClick={() => navigate('/history')}
                    >
                        History
                    </button>
                </div>
            </div>
        </div>
    );
}

export default Dashboard;