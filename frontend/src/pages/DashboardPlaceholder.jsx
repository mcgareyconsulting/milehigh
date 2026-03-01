import QuickSearch from '../components/QuickSearch';

function DashboardPlaceholder() {
  return (
    <div className="flex-1 flex flex-col min-h-0 w-full bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 p-4">
      <QuickSearch />
    </div>
  );
}

export default DashboardPlaceholder;
