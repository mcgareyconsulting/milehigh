/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The drill-through modal from docs/projects-page-mockup.html. Clicking any panel
 *   header opens the full detail for that panel — the panel body is a summary sized by the
 *   user, this is the complete picture regardless of tile size. Transcribed from the mockup's
 *   `.modal-overlay` / `.modal` / `.modal-section` / `.modal-row` rules and its openModal()
 *   behaviour: Escape closes, a click on the backdrop closes, a click inside does not.
 * exports:
 *   PanelModal: the overlay + shell
 *   ModalSection: a titled block inside the body
 *   ModalRow: a label/value line
 * imports_from: [react]
 * imported_by: [components/projects/projectPanels.jsx, pages/GridDemo.jsx]
 * invariants:
 *   - Rendering nothing when `open` is false — the mockup toggles a class, but keeping a
 *     hidden modal mounted would leave its content in the a11y tree.
 */
import { useEffect, useRef } from 'react';

export function PanelModal({ open, title, onClose, children }) {
  const closeRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) {
      if (e.key === 'Escape') onClose?.();
    }
    document.addEventListener('keydown', onKey);
    // Behind a 720px modal the page shouldn't scroll away underneath it.
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[500] flex items-center justify-center p-5 bg-black/80"
      // Only a click that lands on the backdrop itself closes; clicks inside bubble to here
      // but carry a different target, exactly like the mockup's closeModal(event).
      onClick={e => { if (e.target === e.currentTarget) onClose?.(); }}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-[720px] max-h-[85vh] overflow-y-auto rounded-xl
          bg-[#0d1117] border border-[#1e293b] shadow-[0_20px_60px_#000]"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3
          px-5 py-4 bg-[#0d1117] border-b border-[#1e293b]">
          <h2 className="text-[16px] font-bold text-[#f8fafc]">{title}</h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-[20px] leading-none text-[#64748b] px-2 py-1 rounded-md
              hover:bg-[#1e293b] hover:text-[#f8fafc] transition-colors"
          >
            ✕
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function ModalSection({ title, children }) {
  return (
    <section className="mb-5 last:mb-0">
      <h3 className="text-[12px] font-bold uppercase tracking-[0.5px] text-[#64748b]
        mb-2.5 pb-1.5 border-b border-[#1e293b]">
        {title}
      </h3>
      {children}
    </section>
  );
}

export function ModalRow({ label, children, labelClass = '' }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-[13px] border-b border-[#1e293b]/40 last:border-b-0">
      <span className={`text-[#64748b] ${labelClass}`}>{label}</span>
      <span className="text-[#f8fafc] font-medium text-right flex items-center gap-2 flex-wrap justify-end">
        {children}
      </span>
    </div>
  );
}
