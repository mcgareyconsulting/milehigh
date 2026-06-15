/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Read-only modal that renders the in-app changelog (PATCH_NOTES), grouped by release with new/improved/fixed badges.
 * exports:
 *   PatchNotesModal: Portal modal listing release entries newest-first
 * imports_from: [react, react-dom, ../data/patchNotes]
 * imported_by: [frontend/src/components/AppShell.jsx]
 * invariants:
 *   - Renders via createPortal to document.body to escape header/overflow clipping
 *   - No-op render when isOpen is false; Escape and backdrop click both close
 */
import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { PATCH_NOTES } from '../data/patchNotes';

const TYPE_META = {
  new: { label: 'New', className: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' },
  improved: { label: 'Improved', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' },
  fixed: { label: 'Fixed', className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' },
};

export function PatchNotesModal({ isOpen, onClose, isAdmin = false }) {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Non-admins never see admin-only changes; releases left empty are dropped.
  const visibleReleases = PATCH_NOTES
    .map((release) => ({
      ...release,
      changes: release.changes.filter((c) => isAdmin || !c.adminOnly),
    }))
    .filter((release) => release.changes.length > 0);

  const modalContent = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 transition-opacity"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[85vh] flex flex-col transform transition-all"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-5 py-3 rounded-t-xl">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-white leading-tight">What's New</h2>
              <p className="text-xs text-white text-opacity-90 mt-0.5">
                MHMW Brain — release notes
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-white hover:text-gray-200 transition-colors text-2xl font-bold leading-none"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        <div className="px-5 py-4 overflow-y-auto flex-1 space-y-6">
          {visibleReleases.map((release) => (
            <section key={release.version}>
              <div className="flex flex-wrap items-baseline gap-x-2 mb-1">
                <span className="text-sm font-bold text-gray-900 dark:text-slate-100">
                  {release.version}
                </span>
                <span className="text-xs text-gray-500 dark:text-slate-400">
                  {release.date}
                </span>
              </div>
              {release.summary && (
                <p className="text-sm text-gray-600 dark:text-slate-300 mb-3">
                  {release.summary}
                </p>
              )}
              <ul className="space-y-3">
                {release.changes.map((change, idx) => {
                  const meta = TYPE_META[change.type] || TYPE_META.improved;
                  return (
                    <li key={idx} className="border-l-2 border-accent-500 pl-3">
                      <div className="flex flex-wrap items-baseline gap-x-2 mb-0.5">
                        <span
                          className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${meta.className}`}
                        >
                          {meta.label}
                        </span>
                        <span className="text-sm font-semibold text-gray-800 dark:text-slate-200">
                          {change.title}
                        </span>
                      </div>
                      <p className="text-sm text-gray-700 dark:text-slate-300">
                        {change.detail}
                      </p>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>

        <div className="bg-gray-50 dark:bg-slate-700 px-5 py-3 rounded-b-xl border-t border-gray-200 dark:border-slate-600 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-gray-200 dark:bg-slate-600 text-gray-700 dark:text-slate-200 rounded-md text-sm font-medium hover:bg-gray-300 dark:hover:bg-slate-500 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}

export default PatchNotesModal;
