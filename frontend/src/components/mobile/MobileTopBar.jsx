/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The one 56px phone top bar (Option A, docs/design/subs-mobile-option-a.md) shared by the
 *          subcontractor shell and the staff mobile shell: Brain mark (display only), a pill tab
 *          track, and a hamburger. Purely presentational — the shells own auth, badges and the sheet.
 * exports:
 *   MobileTopBar: ({ tabs: [{ to, label, badge? }], onMenu })
 * imports_from: [react-router-dom]
 * imported_by: [components/SubcontractorShell.jsx, components/StaffMobileShell.jsx]
 * invariants:
 *   - Labels only, no icons: "To-Dos (n)" needs the room, and the red count sits inline.
 *   - Styling comes from styles/sub-portal.css (.sub-topbar / .sub-tabs / .sub-tab). The classes
 *     keep their sub- prefix because the sub portal shipped first; both shells share them.
 */
import { NavLink } from 'react-router-dom';

const MENU = <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>;

export default function MobileTopBar({ tabs, onMenu }) {
    return (
        <header className="sub-topbar">
            <span className="sub-logo" role="img" aria-label="MHMW Brain">
                <img src="/bananas-svgrepo-com.svg" alt="" width="22" height="22" />
            </span>
            <nav className="sub-tabs" aria-label="Sections">
                {tabs.map((t) => (
                    <NavLink key={t.to} to={t.to} className={({ isActive }) => `sub-tab${isActive ? ' active' : ''}`}>
                        <span>{t.label}</span>
                        {t.badge > 0 && (
                            <span className="sub-tab-badge" aria-label={`${t.badge} unread`}>{t.badge > 99 ? '99+' : t.badge}</span>
                        )}
                    </NavLink>
                ))}
            </nav>
            <button type="button" className="sub-menu-btn" aria-label="Menu" onClick={onMenu}>{MENU}</button>
        </header>
    );
}
