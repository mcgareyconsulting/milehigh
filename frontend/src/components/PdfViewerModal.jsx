/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Standalone dialog chrome around the hybrid PDF viewer, for surfaces that open a
 *   release's drawings without the release hub (the iPad card view's Release # link).
 *   Replaces the standalone half of the retired PdfVersionHistoryModal.
 * exports:
 *   PdfViewerModal: props { isOpen, releaseId, title, viewerUrl, initialCommentVersionId,
 *     onOpenVersion, onClose }
 * imports_from: [react, react-dom, ./pdfViewer/PdfViewerPane]
 * imported_by: [frontend/src/components/ReleaseNumberLink.jsx, frontend/src/pages/History.jsx,
 *   frontend/src/pages/JobLogContent.jsx]
 * invariants:
 *   - Same panel size as the release hub, so the viewer reads identically in both
 *   - Escape closes the dialog; the pane swallows it first while its title menu is open
 * updated_by_agent: 2026-09-05T00:00:00Z
 */
import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';

import { PdfViewerPane } from './pdfViewer/PdfViewerPane';
import { MODAL_PANEL_SIZE } from '../constants/modalSize';

export function PdfViewerModal({
    isOpen,
    releaseId,
    title = '',
    viewerUrl = '',
    /** Land on this version's comment thread (notification bell click-through). */
    initialCommentVersionId = null,
    onOpenVersion = null,
    onClose,
}) {
    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    if (!isOpen || releaseId == null) return null;

    return createPortal(
        <div
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: 'rgba(10,16,28,.55)', backdropFilter: 'blur(2px)' }}
            onClick={onClose}
        >
            <div
                className="bg-surface flex flex-col border border-hairline-strong overflow-hidden"
                onClick={(e) => e.stopPropagation()}
                style={{
                    ...MODAL_PANEL_SIZE,
                    borderRadius: 14,
                    boxShadow: 'var(--shadow, 0 24px 60px rgba(15,26,48,.22))',
                }}
            >
                <div
                    className="shrink-0 flex items-center justify-between border-b border-hairline bg-surface-2"
                    style={{ padding: '12px 18px' }}
                >
                    <h2 className="font-bold text-ink truncate" style={{ fontSize: 17 }}>
                        {title ? `${title} Drawings` : 'Drawings'}
                    </h2>
                    <button
                        type="button"
                        onClick={onClose}
                        className="grid place-items-center border border-hairline-strong rounded-[7px] bg-surface text-ink-2 hover:text-ink"
                        style={{ width: 28, height: 28 }}
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>

                <PdfViewerPane
                    releaseId={releaseId}
                    label={title}
                    viewerUrl={viewerUrl}
                    initialCommentVersionId={initialCommentVersionId}
                    onOpenVersion={onOpenVersion}
                />
            </div>
        </div>,
        document.body,
    );
}

export default PdfViewerModal;
