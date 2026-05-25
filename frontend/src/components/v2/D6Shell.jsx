/**
 * @milehigh-header
 * schema_version: 1
 * purpose: D6 "merge" design system shell (preview). Translates the D6 standalone prototype
 *   (global header, page action bar, saved-view tabs, quick-filter row, dense spreadsheet table)
 *   into Tailwind, wired to the app's existing ThemeContext (dark) and density (old-man) settings.
 * exports:
 *   D6Layout, D6Header, D6PageBar, D6ViewTabs, D6FilterRow, D6Table, D6Th, D6Td, D6RowNum,
 *   D6StagePill, D6StatusDot, useDensity
 * imports_from: [react, react-router-dom, ../../context/ThemeContext]
 * imported_by: [src/pages/JobLogV2.jsx, src/pages/DwlV2.jsx]
 * invariants:
 *   - Colors via Tailwind utilities + dark: variant (root .dark class from ThemeContext).
 *   - Density (row/header heights, fonts, banana size) derives from isOldMan: on = comfortable, off = compact.
 *   - Read-only preview: action menus/chips are visual; search + view tabs + theme/density are live.
 */
import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useTheme } from '../../context/ThemeContext';

// Density presets mirroring the D6 prototype. isOldMan → comfortable (bigger); otherwise compact.
export function useDensity() {
    const { isOldMan } = useTheme();
    return isOldMan
        ? { rowH: 40, headerH: 44, padX: 14, fontBody: 14, fontHeader: 12.5, fontMeta: 13, banana: 26 }
        : { rowH: 30, headerH: 32, padX: 10, fontBody: 12.5, fontHeader: 11.5, fontMeta: 12.5, banana: 20 };
}

// Tailwind class tokens for the D6 palette (light + dark). Kept in one place so the components read cleanly.
const C = {
    page: 'bg-white text-[#1d1b16] dark:bg-[#15140f] dark:text-[#f4f1e8]',
    surface: 'bg-white dark:bg-[#1a1913]',
    subtle: 'bg-[#f7f6f3] dark:bg-[#1c1b15]',
    rowAlt: 'bg-[#fafaf7] dark:bg-[#1f1e17]',
    rowHi: 'bg-[#eef2fb] dark:bg-[#1f2a44]',
    border: 'border-[#e5e3dd] dark:border-[#2c2a22]',
    borderSt: 'border-[#d8d5cd] dark:border-[#3a3830]',
    text: 'text-[#1d1b16] dark:text-[#f4f1e8]',
    mute: 'text-[#6a665c] dark:text-[#9d9588]',
    faint: 'text-[#9a958a] dark:text-[#6a665c]',
    primary: 'text-[#1e3a8a] dark:text-[#6694ff]',
    primaryBg: 'bg-[#1e3a8a] dark:bg-[#6694ff]',
    accent: 'text-[#d97706] dark:text-[#fbbf24]',
    accentSoft: 'bg-[#fde9c8] dark:bg-[#3d2e10]',
    chip: 'bg-[#f3f1eb] dark:bg-[#26241c]',
};
export const D6C = C;

const mono = 'font-mono [font-variant-numeric:tabular-nums]';

// ── Layout ───────────────────────────────────────────────────────────────────
export function D6Layout({ children }) {
    return (
        <div className={`fixed inset-0 flex flex-col overflow-hidden ${C.page}`} style={{ fontFamily: "'Geist','Inter',-apple-system,system-ui,sans-serif" }}>
            {children}
        </div>
    );
}

// ── 1. Global header ──────────────────────────────────────────────────────────
const NAV = [
    { id: 'job', label: 'Job Log', to: '/job-log-v2' },
    { id: 'draft', label: 'Drafting WL', to: '/dwl-v2' },
    { id: 'evt', label: 'Events', to: '/events' },
    { id: 'inv', label: 'Invoicing', to: '/invoicing-report' },
    { id: 'bug', label: 'Bug Tracker', to: '/board' },
];

function IconBtn({ title, onClick, active, children }) {
    return (
        <button
            type="button"
            title={title}
            onClick={onClick}
            className={`grid place-items-center h-7 w-7 rounded-md transition-colors ${active ? `${C.accent}` : C.mute} hover:bg-[#f3f1eb] dark:hover:bg-[#26241c]`}
        >
            {children}
        </button>
    );
}

export function D6Header({ active }) {
    const { isDark, isOldMan, toggleDark, toggleOldMan } = useTheme();
    const navigate = useNavigate();
    return (
        <header className={`flex items-center gap-4 h-12 px-4 border-b ${C.border} ${C.surface} shrink-0`}>
            <button type="button" onClick={() => navigate('/job-log')} className={`flex items-center gap-2 font-extrabold text-base tracking-tight ${C.primary}`} title="Back to current Job Log">
                <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden><rect x="1.5" y="1.5" width="19" height="19" rx="5" className="fill-[#1e3a8a] dark:fill-[#6694ff]" /><path d="M6 14 L6 7 L9 11.5 L12 7 L12 14 M15 7 L15 14 M14 11h2" stroke="#fff" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                MHMW Brain
            </button>

            <div className={`hidden md:flex items-center gap-2 px-2.5 h-7 rounded-md border ${C.border} ${C.subtle} ${C.mute} w-44`}>
                <SearchIcon />
                <span className="text-xs">Project #</span>
                <span className={`ml-auto text-[10px] ${C.faint} ${C.surface} px-1.5 rounded border ${C.border} ${mono}`}>⌘K</span>
            </div>

            <span className={`hidden lg:inline text-[13px] ${C.mute}`}>Map</span>

            <div className="flex-1" />

            <nav className="hidden md:flex items-center gap-0.5">
                {NAV.map((n) => (
                    <NavLink
                        key={n.id}
                        to={n.to}
                        className={({ isActive }) =>
                            `px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                                (n.id === active || isActive)
                                    ? `${C.primaryBg} text-white font-semibold`
                                    : `${C.text} font-medium hover:bg-[#f3f1eb] dark:hover:bg-[#26241c]`
                            }`
                        }
                    >
                        {n.label}
                    </NavLink>
                ))}
            </nav>

            <span className={`w-px h-5 ${C.border} border-l`} />

            <div className="flex items-center gap-1.5">
                <IconBtn title={isDark ? 'Switch to light' : 'Switch to dark'} onClick={toggleDark}>
                    {isDark ? <SunIcon /> : <MoonIcon />}
                </IconBtn>
                <IconBtn title={isOldMan ? 'Compact density' : 'Comfortable density'} onClick={toggleOldMan} active={isOldMan}>
                    <DensityIcon />
                </IconBtn>
                <div className={`grid place-items-center h-[26px] w-[26px] rounded-full ${C.primaryBg} text-white text-[11px] font-bold`}>DR</div>
            </div>
        </header>
    );
}

// ── 2. Page action bar ──────────────────────────────────────────────────────
function Segmented({ value, options, onChange }) {
    return (
        <div className={`inline-flex p-0.5 rounded-md border ${C.border} ${C.subtle}`}>
            {options.map((o) => {
                const on = o.value === value;
                return (
                    <button
                        key={o.value}
                        type="button"
                        onClick={() => onChange?.(o.value)}
                        className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors ${
                            on ? `${C.surface} ${C.text} font-semibold shadow-sm` : `${C.mute} font-medium`
                        }`}
                    >
                        {o.icon}{o.label}
                    </button>
                );
            })}
        </div>
    );
}

function Menu({ label, icon }) {
    return (
        <div className={`inline-flex items-center gap-1.5 h-[30px] px-2.5 rounded-md border ${C.border} ${C.surface} ${C.text} text-xs font-medium select-none`}>
            {icon}{label}<Chevron />
        </div>
    );
}

export function D6PageBar({ primary, viewMode = 'auto', onViewMode, activeView, children }) {
    return (
        <div className={`flex items-center gap-2 px-4 py-2.5 border-b ${C.border} ${C.surface} shrink-0 overflow-x-auto`}>
            <Segmented
                value={viewMode}
                onChange={onViewMode}
                options={[
                    { value: 'table', label: 'Table', icon: <TableIcon /> },
                    { value: 'cards', label: 'Cards', icon: <CardsIcon /> },
                    { value: 'auto', label: 'Auto', icon: <AutoIcon /> },
                ]}
            />
            <span className={`w-px h-5 ${C.border} border-l mx-1`} />
            <button type="button" className={`inline-flex items-center gap-1.5 h-[30px] px-3 rounded-md ${C.primaryBg} text-white text-xs font-semibold`}>
                <PlusIcon />{primary}
            </button>
            {activeView && (
                <div className={`inline-flex items-center gap-1.5 h-[30px] px-2.5 rounded-md ${C.accentSoft} ${C.accent} text-xs font-semibold`}>
                    <StarIcon />
                    <span>{activeView.label}</span>
                    {activeView.count != null && (
                        <span className="text-[11px] font-semibold px-1.5 rounded-full bg-white/60 dark:bg-white/10">{activeView.count}</span>
                    )}
                    <Chevron />
                </div>
            )}
            <Menu label="Bulk actions" />
            <Menu label="Export" icon={<DownloadIcon />} />
            <Menu label="Print" icon={<PrintIcon />} />
            <div className="flex-1" />
            {children}
            <Menu label="Columns" icon={<LayersIcon />} />
        </div>
    );
}

// ── 3. Saved-view tabs ────────────────────────────────────────────────────────
export function D6ViewTabs({ views, active, onChange }) {
    return (
        <div className={`flex items-end gap-0 px-3.5 h-8 ${C.subtle} border-b ${C.border} shrink-0 overflow-x-auto`}>
            {views.map((v) => {
                const on = v.id === active;
                return (
                    <button
                        key={v.id}
                        type="button"
                        onClick={() => onChange?.(v.id)}
                        className={`flex items-center gap-1.5 px-3.5 pt-1.5 pb-[7px] text-xs whitespace-nowrap rounded-t-md -mb-px border-t-2 ${
                            on
                                ? `${C.surface} ${C.text} font-semibold border-t-[#d97706] dark:border-t-[#fbbf24] border-x ${C.border}`
                                : `${C.mute} font-medium border-t-transparent border-x border-x-transparent`
                        }`}
                    >
                        {v.label}
                        {v.count != null && (
                            <span className={`text-[11px] font-semibold px-1.5 rounded-full ${on ? C.chip : ''} ${on ? C.mute : C.faint} ${mono}`}>{v.count}</span>
                        )}
                    </button>
                );
            })}
            <div className={`flex-1 self-stretch border-b ${C.border}`} />
        </div>
    );
}

// ── 4. Quick-filter row ────────────────────────────────────────────────────────
export function D6FilterRow({ search, onSearch, searchPlaceholder, chips = [], onReset, meta = [], total, updated }) {
    return (
        <div className={`flex items-center gap-2.5 px-4 py-2 border-b ${C.border} ${C.surface} shrink-0 min-h-[44px] flex-wrap`}>
            <div className={`flex items-center gap-2 px-2.5 h-7 rounded-md border ${C.border} ${C.subtle} w-64`}>
                <span className={C.mute}><SearchIcon /></span>
                <input
                    value={search}
                    onChange={(e) => onSearch?.(e.target.value)}
                    placeholder={searchPlaceholder}
                    className={`flex-1 bg-transparent outline-none text-xs ${C.text} placeholder:${C.faint}`}
                />
            </div>

            {chips.map((c, i) => (
                <span key={i} className={`inline-flex items-center gap-1.5 h-[26px] px-2.5 rounded-md text-xs font-medium ${c.active ? `bg-[#dbe4f5] dark:bg-[#1e2a4d] ${C.primary}` : `${C.chip} ${C.text}`}`}>
                    {c.label}{c.value && <span className="font-semibold">{c.value}</span>}
                    <span className="opacity-50"><CloseIcon /></span>
                </span>
            ))}
            <span className={`inline-flex items-center h-[26px] px-2.5 rounded-md border border-dashed ${C.border} ${C.mute} text-xs`}>+ Filter</span>

            <button type="button" onClick={onReset} className={`text-xs font-medium ${C.primary} hover:underline`}>Reset</button>

            <div className="flex-1" />

            <div className={`flex items-center gap-3.5 text-xs ${C.mute} ${mono}`}>
                {meta.map((m, i) => (
                    <span key={i}><span className={C.faint}>{m.k}</span> <strong className={`${C.text} font-semibold`}>{m.v}</strong></span>
                ))}
                {total != null && (<><span className={C.faint}>·</span><span><span className={C.faint}>Total</span> <strong className={`${C.text} font-semibold`}>{total}</strong></span></>)}
                {updated && (<><span className={C.faint}>·</span><span className={C.faint}>Updated {updated}</span></>)}
            </div>
        </div>
    );
}

// ── 5. Spreadsheet table ────────────────────────────────────────────────────────
// Vertical scroll only — columns flex to fill the width so there's no horizontal scroll.
export function D6Table({ children }) {
    return (
        <div className={`flex-1 min-h-0 overflow-y-auto overflow-x-hidden ${C.surface}`}>
            {children}
        </div>
    );
}

export function D6HeaderRow({ children }) {
    const den = useDensity();
    return (
        <div className="flex w-full sticky top-0 z-10" style={{ height: den.headerH }}>
            {children}
        </div>
    );
}

// Proportional flex: `w` is a relative weight (columns share 100% of the width). `fixed` keeps an
// exact px width that never shrinks (used for the banana-code column so the icons never clip).
function flexFor(w, fixed) {
    return fixed ? { flex: `0 0 ${w}px`, minWidth: w } : { flex: `${w} 1 0`, minWidth: 0 };
}

// Header cell. No sort/chevron affordance icons — when `interactive` children (a ColumnHeaderFilter)
// are passed, the whole cell is the clickable trigger that opens the filter/sort popover.
export function D6Th({ children, w = 1, hi, align = 'left', first, interactive, fixed }) {
    const den = useDensity();
    return (
        <div
            className={`flex items-center overflow-hidden ${C.subtle} border-r border-b ${C.border} ${first ? `border-l ${C.border}` : ''} whitespace-nowrap font-semibold ${hi ? C.accent : C.text}`}
            style={{ ...flexFor(w, fixed), padding: interactive ? 0 : `0 9px`, fontSize: den.fontHeader, letterSpacing: 0.15, justifyContent: align === 'right' ? 'flex-end' : align === 'center' ? 'center' : 'flex-start' }}
        >
            {children}
        </div>
    );
}

export function D6Td({ children, w = 1, align = 'left', monoCell, className = '', title, fixed }) {
    const den = useDensity();
    return (
        <div
            title={title}
            className={`flex items-center border-r ${C.border} overflow-hidden whitespace-nowrap ${monoCell ? mono : ''} ${className}`}
            style={{ ...flexFor(w, fixed), height: den.rowH, padding: `0 9px`, fontSize: den.fontBody, justifyContent: align === 'right' ? 'flex-end' : align === 'center' ? 'center' : 'flex-start' }}
        >
            <span className="overflow-hidden text-ellipsis whitespace-nowrap">{children}</span>
        </div>
    );
}

export function D6Row({ index, hi, children }) {
    const den = useDensity();
    return (
        <div className={`flex w-full border-b ${C.border} ${hi ? C.rowHi : index % 2 === 1 ? C.rowAlt : C.surface}`} style={{ minHeight: den.rowH }}>
            {children}
        </div>
    );
}

export function D6StagePill({ children }) {
    return (
        <span className="px-1.5 py-0.5 rounded text-[11.5px] font-semibold bg-[#ede4ff] text-[#7c3aed] dark:bg-[#2d2245] dark:text-[#a78bfa] whitespace-nowrap">
            {children}
        </span>
    );
}

const STATUS_DOT = {
    Approved: 'bg-[#16a34a]', Complete: 'bg-[#16a34a]', Closed: 'bg-[#16a34a]',
    Submitted: 'bg-[#1e3a8a] dark:bg-[#6694ff]',
    'In review': 'bg-[#d97706] dark:bg-[#fbbf24]', Open: 'bg-[#d97706] dark:bg-[#fbbf24]',
    Pending: 'bg-[#fbbf24]', Draft: 'bg-[#9a958a]',
};
export function D6StatusDot({ label }) {
    if (!label) return <span className={C.faint}>—</span>;
    const dot = STATUS_DOT[label] || 'bg-[#6a665c]';
    return (
        <span className="inline-flex items-center gap-1.5">
            <span className={`w-[7px] h-[7px] rounded-full ${dot}`} />
            <span className={`text-[13px] ${C.text}`}>{label}</span>
        </span>
    );
}

// ── Inline icons (lightweight, stroke=currentColor) ────────────────────────────
const sw = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.5 };
const SearchIcon = () => <svg width="14" height="14" viewBox="0 0 14 14" {...sw}><circle cx="6" cy="6" r="4" /><path d="M9.5 9.5l3 3" strokeLinecap="round" /></svg>;
const MoonIcon = () => <svg width="15" height="15" viewBox="0 0 14 14" {...sw}><path d="M11.5 7.5 A4.5 4.5 0 1 1 6.5 2.5 A3.5 3.5 0 0 0 11.5 7.5 Z" /></svg>;
const SunIcon = () => <svg width="15" height="15" viewBox="0 0 14 14" {...sw}><circle cx="7" cy="7" r="2.5" /><path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.7 2.7l1 1M10.3 10.3l1 1M11.3 2.7l-1 1M3.7 10.3l-1 1" /></svg>;
const DensityIcon = () => <svg width="15" height="15" viewBox="0 0 14 14" {...sw}><path d="M2 3h10M2 7h10M2 11h10" strokeLinecap="round" /></svg>;
const TableIcon = () => <svg width="14" height="14" viewBox="0 0 14 14" {...sw}><rect x="1.5" y="2" width="11" height="10" rx="1" /><path d="M1.5 5.5h11M5 5.5v6.5" /></svg>;
const CardsIcon = () => <svg width="14" height="14" viewBox="0 0 14 14" {...sw}><rect x="1.5" y="1.5" width="4.5" height="4.5" rx="0.5" /><rect x="8" y="1.5" width="4.5" height="4.5" rx="0.5" /><rect x="1.5" y="8" width="4.5" height="4.5" rx="0.5" /><rect x="8" y="8" width="4.5" height="4.5" rx="0.5" /></svg>;
const AutoIcon = () => <svg width="14" height="14" viewBox="0 0 14 14" {...sw}><path d="M7 1.5v3M7 9.5v3M1.5 7h3M9.5 7h3M3 3l2 2M9 9l2 2M11 3l-2 2M3 11l2-2" /></svg>;
const PlusIcon = () => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M7 2v10M2 7h10" strokeLinecap="round" /></svg>;
const StarIcon = () => <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M6 1l1.5 3 3.5.5-2.5 2.5.5 3.5L6 9l-3 1.5.5-3.5L1 4.5 4.5 4z" /></svg>;
const DownloadIcon = () => <svg width="14" height="14" viewBox="0 0 14 14" {...sw}><path d="M7 2v7.5M4 7l3 3 3-3M2 12.5h10" /></svg>;
const PrintIcon = () => <svg width="14" height="14" viewBox="0 0 14 14" {...sw}><rect x="3" y="1.5" width="8" height="3" /><rect x="1.5" y="4.5" width="11" height="5" rx="0.5" /><rect x="3" y="9.5" width="8" height="3" /></svg>;
const LayersIcon = () => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><path d="M7 1L1.5 4 7 7l5.5-3z" /><path d="M1.5 7L7 10l5.5-3M1.5 10L7 13l5.5-3" /></svg>;
const CloseIcon = () =><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M3 3l6 6M9 3l-6 6" /></svg>;
const Chevron = () => <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M2 4l3.5 3.5L9 4" /></svg>;
