/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shows a centered call-to-action for a NOT-staff-authenticated visitor on the
 *          landing page. Two distinct cases, not one: a truly anonymous visitor gets the
 *          generic "please log in" CTA; a subcontractor who wandered into the staff area
 *          (old bookmark, mistyped URL, clicked a staff-only link) is already signed in —
 *          telling them to "log in" would be actively wrong, so they get a message that
 *          explains WHY this area isn't for them and a way back to their own tickets.
 * exports:
 *   LoginPrompt: CTA component. Props: subcontractor (the signed-in subcontractor object, or
 *     null/undefined for a truly anonymous visitor).
 * imports_from: [react-router-dom]
 * imported_by: [frontend/src/App.jsx]
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useNavigate } from 'react-router-dom';

function LoginPrompt({ subcontractor }) {
  const navigate = useNavigate();

  if (subcontractor) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <p className="text-gray-600 dark:text-slate-400 text-lg mb-1 max-w-md">
          This area is for MHMW staff only.
        </p>
        <p className="text-gray-500 dark:text-slate-500 text-sm mb-6 max-w-md">
          You're signed in as {subcontractor.contact_name} ({subcontractor.company_name}).
        </p>
        <button
          type="button"
          onClick={() => navigate('/sub/tickets')}
          className="px-6 py-3 text-white bg-accent-500 hover:bg-accent-600 rounded-lg font-medium shadow-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:ring-offset-2"
        >
          Back to my tickets
        </button>
      </div>
    );
  }

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
