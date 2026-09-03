/**
 * @milehigh-header
 * schema_version: 1
 * purpose: In-app confirmation dialog for destructive actions, replacing window.confirm
 *   (which is unstyled, unthemed, and blocks the whole tab).
 * exports:
 *   ConfirmDialog: Portal dialog. Props — isOpen, title, message, confirmLabel,
 *     cancelLabel, tone ('danger'|'default'), busy, onConfirm, onCancel.
 * imports_from: [react, react-dom]
 * imported_by: [frontend/src/components/JobDetailsBody.jsx]
 * invariants:
 *   - Portals to document.body: a `fixed` box nested under a backdrop-filtered ancestor
 *     (the release hub) would resolve against that ancestor and get clipped.
 *   - Escape cancels, and the handler runs in the CAPTURE phase and stops propagation, so
 *     a host modal's own window-level Escape listener does not also close the host.
 *   - Backdrop click cancels; clicks inside the panel never do.
 *   - Cancel takes focus on open, so a stray Enter dismisses rather than destroys.
 *   - Confirm stays mounted while `busy` so the caller can show progress; it is the
 *     caller's job to close the dialog once the action settles.
 */
import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

export function ConfirmDialog({
    isOpen,
    title = 'Are you sure?',
    message = null,
    confirmLabel = 'Delete',
    cancelLabel = 'Cancel',
    tone = 'danger',
    busy = false,
    onConfirm,
    onCancel,
}) {
    const cancelRef = useRef(null);

    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => {
            if (e.key !== 'Escape') return;
            // Capture phase + stopPropagation: the host modal listens for Escape on
            // window too, and closing it out from under this dialog loses the user's
            // place entirely.
            e.stopPropagation();
            if (!busy) onCancel?.();
        };
        window.addEventListener('keydown', onKey, true);
        return () => window.removeEventListener('keydown', onKey, true);
    }, [isOpen, busy, onCancel]);

    useEffect(() => {
        if (isOpen) cancelRef.current?.focus();
    }, [isOpen]);

    if (!isOpen) return null;

    const confirmStyle = tone === 'danger'
        ? { background: 'var(--fl-red-bg)', color: 'var(--fl-red-fg)' }
        : { background: 'var(--accent)', color: 'var(--accent-ink)' };

    const dialog = (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4"
            style={{ background: 'rgba(10,16,28,.55)' }}
            onClick={() => { if (!busy) onCancel?.(); }}
        >
            <div
                className="bg-surface border border-hairline-strong"
                style={{
                    width: 'min(420px, 92vw)',
                    borderRadius: 14,
                    boxShadow: 'var(--shadow)',
                    padding: '20px 22px 18px',
                }}
                onClick={(e) => e.stopPropagation()}
                role="alertdialog"
                aria-modal="true"
                aria-label={title}
            >
                <h2 className="text-ink" style={{ fontWeight: 700, fontSize: 16, letterSpacing: '-.2px' }}>
                    {title}
                </h2>
                {message && (
                    <p className="text-ink-2" style={{ fontSize: 13.5, marginTop: 8, lineHeight: 1.5 }}>
                        {message}
                    </p>
                )}
                <div className="flex items-center justify-end" style={{ gap: 8, marginTop: 18 }}>
                    <button
                        ref={cancelRef}
                        type="button"
                        onClick={() => onCancel?.()}
                        disabled={busy}
                        className="font-semibold border border-hairline-strong bg-surface text-ink-2 cursor-pointer disabled:opacity-50"
                        style={{ fontSize: 13, padding: '7px 14px', borderRadius: 8 }}
                    >
                        {cancelLabel}
                    </button>
                    <button
                        type="button"
                        onClick={() => onConfirm?.()}
                        disabled={busy}
                        className="font-semibold border-0 cursor-pointer disabled:opacity-60"
                        style={{ ...confirmStyle, fontSize: 13, padding: '7px 14px', borderRadius: 8 }}
                    >
                        {busy ? 'Working…' : confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );

    return createPortal(dialog, document.body);
}

export default ConfirmDialog;
