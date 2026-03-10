import { useNavigate } from 'react-router-dom';

function LoginPrompt() {
  const navigate = useNavigate();

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
      <p className="text-gray-600 dark:text-slate-400 text-lg mb-6 max-w-md">
        Please log in to access Job Log, Events, and Drafting Work Load.
      </p>
      <button
        type="button"
        onClick={() => navigate('/login')}
        className="px-6 py-3 text-white bg-accent-500 hover:bg-accent-600 rounded-lg font-medium shadow-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:ring-offset-2"
      >
        Log in
      </button>
    </div>
  );
}

export default LoginPrompt;
