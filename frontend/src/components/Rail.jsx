/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Collapsible left icon rail that replaces the top nav bar at >=1440px when Left Sidebar Mode is on (opt-in via ThemeContext; top header is default). Per Aug 2026 Job Log redesign handoff (docs/design/job-log-redesign/README.md §1).
 * exports:
 *   Rail: Left navigation rail. Props: isAdmin, canSeeReport, onLogout, onOpenPatchNotes.
 * imports_from: [react, react-dom, react-router-dom, ../context/ThemeContext, ../context/LocationContext, ./QuickSearch]
 * imported_by: [frontend/src/components/AppShell.jsx]
 * invariants:
 *   - Never scrolls. The content budget (logo 38 + 15 items x 37 + footer 3 x 37 + dividers) must fit the
 *     viewport; a new nav item means shrinking ITEM_H, not adding overflow.
 *   - Notifications live as the floating corner pod on AppShell main (not a rail row).
 *   - Open/collapsed state persists in localStorage under RAIL_KEY.
 *   - Tooltips and popovers portal to document.body: the rail clips its own children so labels
 *     don't spill during the width transition, which would otherwise clip them too.
 *   - Routes, labels and role gating mirror AppShell's top bar exactly — the rail is a
 *     presentation swap, not a different information architecture.
 *   - Mounted only when AppShell's isSidebarMode is true; theme panel can turn the mode off.
 * updated_by_agent: 2026-08-06T00:00:00Z
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useLocation } from 'react-router-dom';

import { useTheme } from '../context/ThemeContext';
import { useLocationContext } from '../context/LocationContext';
import QuickSearch from './QuickSearch';
import { CURRENT_VERSION } from '../data/patchNotes';

const RAIL_KEY = 'mhmw_rail_open';
// Collapsed: icon column only. 52px + 7px side pad fits the 38px logo without
// the empty gutters the old 60px width left around the icons.
const RAIL_COLLAPSED = 52;
const RAIL_EXPANDED = 212;

// Handoff spec: 37px rows, and the rail must never scroll. Those two only
// coexist on a tall enough window — a full admin rail is 18 rows, which needs
// ~770px and silently loses its last items (Matching) on a short laptop. The
// README's own instruction for that case is to reduce item height rather than
// allow scroll, so the height is computed from the viewport and only reaches
// the spec's 37px when there's room for it.
const ITEM_H_MAX = 37;
const ITEM_H_MIN = 26;
// Padding (18) + logo (38) + two dividers with their margins (19 + 17).
const RAIL_CHROME_H = 92;
const FOOTER_ITEMS = 3;

function fitItemHeight(viewportH, mainItemCount) {
    const rows = mainItemCount + FOOTER_ITEMS;
    const gaps = Math.max(0, mainItemCount - 1) + (FOOTER_ITEMS - 1);
    const usable = viewportH - RAIL_CHROME_H - gaps;
    const h = Math.floor(usable / rows);
    return Math.max(ITEM_H_MIN, Math.min(ITEM_H_MAX, h));
}

// 24-viewBox stroke icons at the handoff's spec (1.7px stroke, round caps).
// Path data is taken verbatim from the prototype's nav table so the rail's
// silhouette matches the design rather than approximating it with the app's
// older 2px-stroke icon set.
const ICON = {
    search: 'M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0 M20 20l-3.6-3.6',
    map: 'M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z M9 3v15 M15 6v15',
    locations: 'M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z M12 10m-2.2 0a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0 -4.4 0',
    projects: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
    jobLog: 'M3 5h18v14H3z M3 10h18 M9 5v14',
    drafting: 'M4 20l4-1 10-10-3-3L5 16z M14 6l3 3',
    events: 'M4 6h16v14H4z M4 10h16 M8 3v4 M16 3v4',
    todos: 'M4 5h16v14H4z M8 12l3 3 5-6',
    installSchedule: 'M3 7h11v8H3z M14 10h4l3 3v2h-7z M7 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0 M17 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0',
    invoicing: 'M6 3h12v18l-3-2-3 2-3-2-3 2z M9 8h6 M9 12h6',
    subs: 'M9 11m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0 M3 20c0-3.3 2.7-5 6-5s6 1.7 6 5 M17 7.6a3.4 3.4 0 0 1 0 6.8 M18 20c0-2.4-.9-3.9-2.4-4.6',
    meetings: 'M3 7h11v10H3z M14 11l6-3v8l-6-3z',
    bug: 'M9 6a3 3 0 0 1 6 0 M6 10h12v4a6 6 0 0 1-12 0z M3 11h3 M18 11h3 M4 6l2.5 2 M20 6l-2.5 2 M4 18l2.5-2 M20 18l-2.5-2',
    tm: 'M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0 M12 7v5l3 2',
    matching: 'M4 7h4l8 10h4 M4 17h4l8-10h4 M18 4l3 3-3 3 M18 14l3 3-3 3',
    collapse: 'M11 6l-6 6 6 6 M19 6l-6 6 6 6',
    expand: 'M5 6l6 6-6 6 M13 6l6 6-6 6',
    sun: 'M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0 M12 2v2 M12 20v2 M2 12h2 M20 12h2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M19.1 4.9l-1.4 1.4 M6.3 17.7l-1.4 1.4',
    moon: 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z',
    logout: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3 M10 8l-4 4 4 4 M6 12h11',
};

// The icon strings above hold several subpaths in one `d` (…z M3 10h18…), which
// is valid SVG — no need to split them into separate <path> elements.
function RailIcon({ d }) {
    return (
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d={d} />
        </svg>
    );
}

/**
 * One row shape for every rail entry — route links, toggles and panel triggers
 * differ only in what onClick does and how "active" is decided.
 *
 * Module-level on purpose: defined inside Rail it would be a new component type
 * on every render, remounting all 19 rows (and killing hover state mid-gesture).
 */
function RailItem({ icon, label, active, onClick, badge = 0, trigger, open, onHover, onLeave, itemH }) {
    return (
        <button
            type="button"
            onClick={onClick}
            onMouseEnter={(e) => { onHover(e, label); if (!active) e.currentTarget.style.background = 'var(--rail-hover)'; }}
            onMouseLeave={(e) => { onLeave(); if (!active) e.currentTarget.style.background = 'transparent'; }}
            onFocus={(e) => onHover(e, label)}
            onBlur={onLeave}
            data-rail-trigger={trigger || undefined}
            aria-label={label}
            aria-current={active ? 'page' : undefined}
            className="relative w-full flex items-center rounded-lg transition-colors shrink-0"
            style={{
                height: itemH,
                justifyContent: open ? 'flex-start' : 'center',
                padding: open ? '0 10px' : 0,
                gap: open ? 12 : 0,
                background: active ? 'var(--rail-active)' : 'transparent',
                color: active ? 'var(--rail-fg-active)' : 'var(--rail-fg)',
            }}
        >
            <span className="shrink-0 grid place-items-center" style={{ width: 19, height: 19 }}>
                <RailIcon d={icon} />
            </span>
            {open && (
                <span className="truncate" style={{ fontSize: 12.5, fontWeight: 600 }}>{label}</span>
            )}
            {open && <span className="flex-1" />}
            {badge > 0 && (
                <span
                    className="grid place-items-center font-bold text-white"
                    style={{
                        background: '#e0483c',
                        borderRadius: 999,
                        fontSize: 10,
                        minWidth: 17,
                        height: 17,
                        padding: '0 5px',
                        // Collapsed, the badge floats over the icon and needs a
                        // rail-colored ring to stay legible against it.
                        position: open ? 'static' : 'absolute',
                        top: open ? undefined : 4,
                        right: open ? undefined : 9,
                        boxShadow: open ? 'none' : '0 0 0 2px var(--rail-bg)',
                    }}
                >
                    {badge > 99 ? '99+' : badge}
                </span>
            )}
        </button>
    );
}

export default function Rail({
    isAdmin,
    canSeeReport,
    onLogout,
    onOpenPatchNotes,
}) {
    const navigate = useNavigate();
    const location = useLocation();
    const { isDark, isOldMan, isSidebarMode, toggleDark, toggleOldMan, toggleSidebarMode } = useTheme();
    const { locationEnabled, locationRequesting, handleLocationToggle } = useLocationContext();

    const [open, setOpen] = useState(() => localStorage.getItem(RAIL_KEY) === 'true');
    const [tip, setTip] = useState(null);       // { label, top } while collapsed
    const [panel, setPanel] = useState(null);   // 'search' | 'theme' | null
    const [panelTop, setPanelTop] = useState(0);
    const [viewportH, setViewportH] = useState(() => window.innerHeight);
    const navRef = useRef(null);

    // The rail is h-screen, so the viewport height is its height. Watching the
    // window directly (rather than the nav) avoids a measure/resize feedback
    // loop, since the thing being measured is what the measurement changes.
    useEffect(() => {
        const onResize = () => setViewportH(window.innerHeight);
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);

    useEffect(() => {
        localStorage.setItem(RAIL_KEY, String(open));
    }, [open]);

    // Collapsing while a tooltip is up would strand it — the item it points at
    // has already moved.
    useEffect(() => { setTip(null); }, [open]);

    useEffect(() => {
        if (!panel) return;
        const onDown = (e) => {
            if (!e.target.closest('[data-rail-panel]') && !e.target.closest('[data-rail-trigger]')) {
                setPanel(null);
            }
        };
        const onKey = (e) => { if (e.key === 'Escape') setPanel(null); };
        document.addEventListener('mousedown', onDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [panel]);

    // A route change means the search panel's results are stale context.
    useEffect(() => { setPanel(null); }, [location.pathname]);

    const isActive = (path) => location.pathname.startsWith(path);

    const showTip = useCallback((e, label) => {
        if (open) return;
        const r = e.currentTarget.getBoundingClientRect();
        setTip({ label, top: r.top + r.height / 2 });
    }, [open]);

    const openPanel = (e, key) => {
        const r = e.currentTarget.getBoundingClientRect();
        setPanelTop(r.top);
        setPanel((prev) => (prev === key ? null : key));
        setTip(null);
    };

    const railW = open ? RAIL_EXPANDED : RAIL_COLLAPSED;

    // Fixed rows (Search, Map, Locations, Projects, Job Log, Drafting WL,
    // Events, To-Dos, Install Schedule) plus whatever this user's role unlocks.
    // Notifications are the floating pod on AppShell, not a rail row.
    const mainItemCount =
        9 +
        (canSeeReport ? 1 : 0) +
        (isAdmin ? 5 : 0);
    const itemH = fitItemHeight(viewportH, mainItemCount);

    const hideTip = useCallback(() => setTip(null), []);
    const itemProps = { open, onHover: showTip, onLeave: hideTip, itemH };

    const routeItem = (path, label, icon) => (
        <RailItem key={path} icon={icon} label={label} active={isActive(path)}
            onClick={() => navigate(path)} {...itemProps} />
    );

    return (
        <>
            <nav
                ref={navRef}
                className="flex flex-col shrink-0 relative z-20"
                style={{
                    width: railW,
                    transition: 'width .18s ease',
                    background: 'var(--rail-bg)',
                    borderRight: '1px solid var(--rail-border)',
                    // Slightly tighter side pad when collapsed so the narrower
                    // rail still centers the 38px logo/icons without clipping.
                    padding: open ? '10px 9px 8px' : '10px 7px 8px',
                }}
                aria-label="Main navigation"
            >
                {/* Logo — opens patch notes, per handoff §1. */}
                <button
                    type="button"
                    onClick={onOpenPatchNotes}
                    onMouseEnter={(e) => showTip(e, 'Patch notes')}
                    onMouseLeave={() => setTip(null)}
                    className="flex items-center shrink-0 overflow-hidden rounded-lg"
                    style={{ gap: 10, height: 38 }}
                    aria-label="Patch notes"
                >
                    <span
                        className="shrink-0 grid place-items-center"
                        style={{
                            width: 38, height: 38, borderRadius: 9,
                            background: 'linear-gradient(180deg,#3a6ae0,#22409a)',
                        }}
                    >
                        <img src="/bananas-svgrepo-com.svg" alt="" width="21" height="21" />
                    </span>
                    {open && (
                        <span className="min-w-0 text-left">
                            <span className="block truncate text-white" style={{ fontSize: 13, fontWeight: 700 }}>
                                MHMW Brain
                            </span>
                            <span className="block truncate" style={{ fontSize: 10.5, color: 'var(--rail-fg)' }}>
                                {CURRENT_VERSION} · patch notes
                            </span>
                        </span>
                    )}
                </button>

                <div className="shrink-0" style={{ height: 1, background: 'var(--rail-border)', margin: '10px 0 8px' }} />

                {/* Item list. Clipped, never scrolled — see the invariant above. */}
                <div className="flex flex-col flex-1 min-h-0 overflow-hidden" style={{ gap: 1 }}>
                    <RailItem icon={ICON.search} label="Search" active={panel === 'search'}
                        trigger="search" onClick={(e) => openPanel(e, 'search')} {...itemProps} />
                    {routeItem('/jobsite-map', 'Map', ICON.map)}
                    <RailItem
                        icon={ICON.locations}
                        label={locationEnabled ? 'Locations — on' : 'Locations'}
                        active={locationEnabled}
                        onClick={locationRequesting ? undefined : handleLocationToggle}
                        {...itemProps}
                    />
                    {routeItem('/projects', 'Projects', ICON.projects)}
                    {routeItem('/job-log', 'Job Log', ICON.jobLog)}
                    {routeItem('/drafting-work-load', 'Drafting WL', ICON.drafting)}
                    {routeItem('/events', 'Events', ICON.events)}
                    {routeItem('/todos', 'To-Dos', ICON.todos)}
                    {routeItem('/install-schedule', 'Install Schedule', ICON.installSchedule)}
                    {canSeeReport && routeItem('/invoicing-report', 'Invoicing', ICON.invoicing)}
                    {isAdmin && routeItem('/subs', 'Subs', ICON.subs)}
                    {isAdmin && routeItem('/meetings', 'Meetings', ICON.meetings)}
                    {/* Handoff calls this "Bug Reports"; the app renamed it to
                        Ongoing Complaints in #323, which is the newer decision. */}
                    {isAdmin && routeItem('/board', 'Ongoing Complaints', ICON.bug)}
                    {isAdmin && routeItem('/tm-tickets', 'T&M', ICON.tm)}
                    {isAdmin && routeItem('/admin/submittal-matching', 'Matching', ICON.matching)}
                </div>

                <div className="shrink-0" style={{ height: 1, background: 'var(--rail-border)', margin: '8px 0' }} />

                <div className="flex flex-col shrink-0 overflow-hidden" style={{ gap: 1 }}>
                    <RailItem
                        icon={open ? ICON.collapse : ICON.expand}
                        label={open ? 'Collapse' : 'Expand'}
                        onClick={() => setOpen((v) => !v)}
                        {...itemProps}
                    />
                    <RailItem
                        icon={isDark ? ICON.sun : ICON.moon}
                        label="Appearance"
                        active={panel === 'theme'}
                        trigger="theme"
                        onClick={(e) => openPanel(e, 'theme')}
                        {...itemProps}
                    />
                    <RailItem icon={ICON.logout} label="Logout" onClick={onLogout} {...itemProps} />
                </div>
            </nav>

            {/* Tooltip. Portaled and fixed: the rail clips its own children, so an
                in-tree tooltip would be cut off at the collapsed edge. */}
            {tip && !open && createPortal(
                <div
                    className="dc-fade"
                    style={{
                        position: 'fixed', left: RAIL_COLLAPSED + 6, top: tip.top,
                        transform: 'translateY(-50%)', background: '#0b1220', color: '#fff',
                        border: '1px solid #2a3550', borderRadius: 7, padding: '6px 10px',
                        fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap',
                        pointerEvents: 'none', boxShadow: '0 8px 22px rgba(0,0,0,.35)', zIndex: 60,
                    }}
                    role="tooltip"
                >
                    {tip.label}
                </div>,
                document.body
            )}

            {panel === 'search' && createPortal(
                <div
                    data-rail-panel
                    className="dc-pop"
                    style={{
                        position: 'fixed', left: railW + 6, top: panelTop, width: 420, zIndex: 60,
                        background: 'var(--surface)', border: '1px solid var(--border-strong)',
                        borderRadius: 12, boxShadow: 'var(--shadow)', padding: 12,
                    }}
                >
                    <QuickSearch />
                </div>,
                document.body
            )}

            {panel === 'theme' && createPortal(
                <div
                    data-rail-panel
                    className="dc-pop"
                    style={{
                        position: 'fixed', left: railW + 6, top: panelTop - 100, width: 220, zIndex: 60,
                        background: 'var(--surface)', border: '1px solid var(--border-strong)',
                        borderRadius: 12, boxShadow: 'var(--shadow)', padding: 12,
                    }}
                >
                    <ThemeToggleRow label="Dark Mode" on={isDark} onToggle={toggleDark} />
                    <div style={{ height: 10 }} />
                    <ThemeToggleRow label="Old Man Mode" on={isOldMan} onToggle={toggleOldMan} amber />
                    <div style={{ height: 10 }} />
                    <ThemeToggleRow
                        label="Left Sidebar Mode"
                        on={isSidebarMode}
                        onToggle={toggleSidebarMode}
                    />
                </div>,
                document.body
            )}
        </>
    );
}

// Old Man Mode is a third theme axis the handoff's rail has no slot for; it
// rides here with dark mode so neither is lost when the top bar goes away.
function ThemeToggleRow({ label, on, onToggle, amber = false }) {
    return (
        <div className="flex items-center justify-between gap-3">
            <span className="text-ink" style={{ fontSize: 12.5, fontWeight: 600 }}>{label}</span>
            <button
                type="button"
                onClick={onToggle}
                aria-pressed={on}
                aria-label={label}
                className="relative shrink-0 rounded-full transition-colors"
                style={{
                    width: 40, height: 22,
                    background: on ? (amber ? '#d68910' : 'var(--accent)') : 'var(--border-strong)',
                }}
            >
                <span
                    className="absolute rounded-full bg-white shadow transition-transform"
                    style={{ top: 2, left: 2, width: 18, height: 18, transform: on ? 'translateX(18px)' : 'none' }}
                />
            </button>
        </div>
    );
}
