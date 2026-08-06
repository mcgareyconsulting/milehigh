/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Portal modal that displays the contextual events list for a release or submittal without leaving the JL or DWL page.
 * exports:
 *   EventsModal: Portal modal wrapping EventsList with filter props baked in (submittalId or job+release)
 * imports_from: [react, react-dom, ./EventsList]
 * imported_by: [frontend/src/components/JobDetailsBody.jsx, frontend/src/components/SubmittalDetailsModal.jsx]
 * invariants:
 *   - Renders via createPortal so stacking on top of parent detail modal works regardless of DOM nesting
 *   - Escape key and backdrop click close only this modal, not the parent
 */
import { useEffect } from 'react';
import { createPortal } from 'react-dom';

import { EventsList } from './EventsList';

export function EventsModal({ isOpen, onClose, title = 'Events', submittalId, jobFilter, releaseFilter }) {
    useEffect(() => {
        if (!isOpen) return;
        const handleKey = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                onClose();
            }
        };
        document.addEventListener('keydown', handleKey);
        return () => document.removeEventListener('keydown', handleKey);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const modal = (
        <div
            className="fixed inset-0 z-[55] flex items-center justify-center bg-black bg-opacity-50 p-4"
            onClick={onClose}
        >
            <div
                className="bg-surface rounded-[14px] shadow-2xl w-full max-w-6xl h-[85vh] flex flex-col dc-pop"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-surface-2 border-b border-hairline px-4 py-3 rounded-t-[14px] flex-shrink-0">
                    <div className="flex items-center justify-between">
                        <h2 className="text-base font-bold text-ink">{title}</h2>
                        <button
                            onClick={onClose}
                            className="text-ink-3 hover:text-ink transition-colors text-2xl font-bold leading-none"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                </div>
                <div className="p-3 flex flex-col flex-1 min-h-0">
                    <EventsList
                        submittalId={submittalId}
                        jobFilter={jobFilter}
                        releaseFilter={releaseFilter}
                    />
                </div>
            </div>
        </div>
    );

    return createPortal(modal, document.body);
}

export default EventsModal;
