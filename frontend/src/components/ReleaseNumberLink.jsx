/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Renders a Job Log release number as clean inline text (matching the Job # styling) that opens the FC drawing. Clicking opens the version-history hub (pick a version to view/edit, upload a new one, or jump to Procore from the top) for drafters/admins or any release with an uploaded drawing; a Procore-only release links straight to Procore. Built for the iPad/touch card view where the JobsTableRow Release # cell chrome is too heavy.
 * exports:
 *   default ReleaseNumberLink: Props — value, releaseId, hasDrawing, viewerUrl, canMarkup.
 * imports_from: [react, ./PdfMarkupModal, ./PdfVersionHistoryModal]
 * imported_by: [frontend/src/components/JobLogRow.jsx]
 * invariants:
 *   - Typography matches the Job # span in JobLogRow (font-mono, text-sm, font-semibold); only the color signals interactivity.
 *   - canMarkup || hasDrawing → version-history hub (read-only users open versions in view mode); else Procore link; else plain text.
 *   - Click handlers stopPropagation so tapping never toggles the card row.
 */
import React, { useEffect, useState } from 'react';
import { PdfMarkupModal } from './PdfMarkupModal';
import { PdfVersionHistoryModal } from './PdfVersionHistoryModal';

const baseCls = 'font-mono text-sm font-semibold align-baseline';
const linkCls = `${baseCls} text-blue-600 dark:text-blue-400 hover:underline cursor-pointer bg-transparent border-0 p-0 leading-none`;

export default function ReleaseNumberLink({
    value,
    releaseId,
    hasDrawing = false,
    viewerUrl = '',
    canMarkup = false,
}) {
    const [historyOpen, setHistoryOpen] = useState(false);
    const [markupOpen, setMarkupOpen] = useState(false);
    const [markupVersionId, setMarkupVersionId] = useState(null);
    const [markupMode, setMarkupMode] = useState('view');
    const [hasDrawingLocal, setHasDrawingLocal] = useState(Boolean(hasDrawing));

    useEffect(() => { setHasDrawingLocal(Boolean(hasDrawing)); }, [hasDrawing]);

    const hasViewer = viewerUrl && viewerUrl.trim() !== '';

    // Clicking the number opens the version-history hub: drafters/admins (to
    // upload/manage) and any release with an uploaded drawing (to pick a version
    // to view) route here. The hub surfaces the Procore link at the top.
    if (canMarkup || hasDrawingLocal) {
        return (
            <>
                <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setHistoryOpen(true); }}
                    className={linkCls}
                    title="Drawing versions — view, edit, upload, or open in Procore"
                >
                    {value}
                </button>
                <PdfVersionHistoryModal
                    isOpen={historyOpen}
                    releaseId={releaseId}
                    viewerUrl={viewerUrl}
                    onClose={() => setHistoryOpen(false)}
                    onOpenVersion={(vid, mode) => {
                        setHistoryOpen(false);
                        setMarkupVersionId(vid);
                        setMarkupMode(canMarkup ? mode : 'view');
                        setMarkupOpen(true);
                    }}
                />
                <PdfMarkupModal
                    isOpen={markupOpen}
                    releaseId={releaseId}
                    versionId={markupVersionId}
                    mode={markupMode}
                    onClose={() => setMarkupOpen(false)}
                    onSaved={() => setHasDrawingLocal(true)}
                />
            </>
        );
    }

    if (hasViewer) {
        return (
            <a
                href={viewerUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={linkCls}
                onClick={(e) => e.stopPropagation()}
                title="Open Procore viewer"
            >
                {value}
            </a>
        );
    }

    return <span className={`${baseCls} text-gray-900 dark:text-slate-100`}>{value}</span>;
}
