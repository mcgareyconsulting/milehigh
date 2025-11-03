import { useNavigate } from 'react-router-dom';

function Dashboard() {
    const navigate = useNavigate();

    const cards = [
        {
            title: 'Operations',
            description: 'View and monitor sync operations',
            icon: '⚙️',
            gradient: 'from-accent-500 to-accent-600',
            hoverGradient: 'hover:from-accent-600 hover:to-accent-700',
            onClick: () => navigate('/operations')
        },
        {
            title: 'History',
            description: 'Browse job change history',
            icon: '📊',
            gradient: 'from-accent-400 to-accent-500',
            hoverGradient: 'hover:from-accent-500 hover:to-accent-600',
            onClick: () => navigate('/history')
        }
    ];

    return (
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-12 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-6xl mx-auto w-full" style={{ width: '100%', maxWidth: '1152px' }}>
                <div className="text-center mb-12">
                    <h1 className="text-5xl font-bold bg-gradient-to-r from-accent-500 to-accent-600 bg-clip-text text-transparent mb-4">
                        Mile High Metal Works Operations Dashboard
                    </h1>
                    <p className="text-gray-600 text-lg max-w-2xl mx-auto">
                        Monitor sync operations and track job changes across your systems
                    </p>
                </div>

                <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
                    {cards.map((card, index) => (
                        <div
                            key={index}
                            onClick={card.onClick}
                            className="group relative bg-white rounded-2xl shadow-lg hover:shadow-2xl transition-all duration-300 cursor-pointer overflow-hidden transform hover:-translate-y-2"
                        >
                            <div className={`absolute inset-0 bg-gradient-to-br ${card.gradient} opacity-0 group-hover:opacity-5 transition-opacity duration-300`}></div>
                            <div className="p-8 relative z-10">
                                <div className="text-6xl mb-4 transform group-hover:scale-110 transition-transform duration-300">
                                    {card.icon}
                                </div>
                                <h2 className="text-2xl font-bold text-gray-800 mb-2 group-hover:text-accent-600 transition-colors">
                                    {card.title}
                                </h2>
                                <p className="text-gray-600 mb-6">
                                    {card.description}
                                </p>
                                <div className={`inline-flex items-center px-6 py-3 bg-gradient-to-r ${card.gradient} ${card.hoverGradient} text-white font-semibold rounded-lg shadow-md group-hover:shadow-xl transition-all duration-300 transform group-hover:scale-105`}>
                                    <span>Explore</span>
                                    <span className="ml-2 transform group-hover:translate-x-1 transition-transform">→</span>
                                </div>
                            </div>
                            <div className={`absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r ${card.gradient} transform scale-x-0 group-hover:scale-x-100 transition-transform duration-300`}></div>
                        </div>
                    ))}
                </div>

                <div className="mt-16 text-center">
                    <div className="inline-block bg-white rounded-xl shadow-md p-6 max-w-md">
                        <h3 className="text-lg font-semibold text-gray-800 mb-2">Quick Stats</h3>
                        <p className="text-gray-600 text-sm">
                            Use the navigation menu to access detailed operations and history views
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Dashboard;