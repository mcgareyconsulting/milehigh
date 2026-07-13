/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Persistent shell for the three release views (Table / Board / Timeline). Renders the Job Log toolbar + filter state ONCE and stays mounted across the view switch (pathless layout route), so only the Outlet content swaps. The toolbar's Projects / quick-filter / Search controls drive both the table and the PM Board.
 * exports:
 *   ReleasesLayout: Layout route element owning useReleases + useJobsFilters + the toolbar, Actions handlers, and modals; provides filtered data to child views via <Outlet context>.
 * imports_from: [react, react-router-dom, ../context/ThemeContext, ../hooks/useJumpToHighlight, ../context/ReleasesContext, ../hooks/useJobsFilters, ../hooks/useBreakpoint, ../components/JobLogQuickFilters, ../components/ProjectFilterDropdown, ../components/ActiveFilterChips, ../components/ReleasesViewSwitcher, ../components/Dropdown, ../services/jobsApi, ../utils/auth, ../utils/jobLogPdf, ../utils/jobLogColumns]
 * imported_by: [../App.jsx]
 * invariants:
 *   - Lives mounted across /job-log ↔ /pm-board navigation (pathless parent route), so filter state + header DOM persist; the search input keeps focus across a view switch.
 *   - displayJobs (table) applies project + subset + search + column-header filters + sort; boardJobs (PM Board) applies ONLY project + subset + search.
 *   - Actions (Export CSV / Print / Archive / Renumber / New Release) resolve here because the toolbar is always mounted while the table content may not be.
 */
import React, { useMemo, useEffect, useState, useCallback, useRef } from 'react';
import { useTheme } from '../context/ThemeContext';
import { useNavigate, useSearchParams, useLocation, Outlet } from 'react-router-dom';
import { useJumpToHighlight } from '../hooks/useJumpToHighlight';
import { useReleases } from '../context/ReleasesContext';
import { useJobsFilters } from '../hooks/useJobsFilters';
import { useBreakpoint } from '../hooks/useBreakpoint';
import JobLogQuickFilters from '../components/JobLogQuickFilters';
import ProjectFilterDropdown from '../components/ProjectFilterDropdown';
import ActiveFilterChips from '../components/ActiveFilterChips';
import ReleasesViewSwitcher from '../components/ReleasesViewSwitcher';
import ViewToggle, { useViewMode } from '../components/ViewToggle';
import Dropdown, { DropdownItem } from '../components/Dropdown';
import { jobsApi } from '../services/jobsApi';
import { checkAuth, userCanAccessKatieFilter } from '../utils/auth';
import { generateJobLogReviewPdf } from '../utils/jobLogPdf';
import { reviewSort, columnOrder, COLUMN_WIDTH_PERCENT, FILTERABLE_COLUMNS } from '../utils/jobLogColumns';

// Friendly labels + display order for the active-filter chips (keys match the column-filter keys).
const JL_FILTER_LABELS = {
    'Job #': 'Job',
    'Release #': 'Release',
    'Job': 'Job Name',
    'PM': 'PM',
    'BY': 'By',
    'Stage': 'Stage',
    'Fab Order': 'Fab Order',
    'Paint color': 'Paint Color',
    'Job Comp': 'Install Prog',
    'Invoiced': 'Invoiced',
};
const JL_FILTER_CHIP_ORDER = ['Job #', 'Release #', 'Job', 'PM', 'BY', 'Stage', 'Fab Order', 'Paint color', 'Job Comp', 'Invoiced'];

function ReleasesLayout() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const location = useLocation();
    const { jobs, columns, loading, error: fetchError, lastUpdated, refetch, fetchAll } = useReleases();
    const { isOldMan } = useTheme();
    const { isMobile, isTablet, isBelowLg, isDesktop } = useBreakpoint();

    // Which child view is active — the Board ignores column-header filters, so the
    // toolbar's record count must follow boardJobs there; table-only memos (e.g.
    // uniqueValuesByColumn) can also skip their work while the table is unmounted.
    const onBoardRoute = location.pathname.startsWith('/pm-board');

    // User-selectable view (persisted), reconciled with the device width:
    //  - 'auto'  → phone: big card, tablet: expandable rows, desktop: table (default)
    //  - 'table' → full table (honored from tablet-landscape width up; see enforcement below)
    //  - 'cards' → tiles on phone, dense expandable rows on tablet/desktop
    // ENFORCED below lg (< 1024px — phones and portrait tablets): card mode always. The full
    // table can't render usefully at those widths, so the ViewToggle's Table pick only
    // applies from tablet-landscape up (and the toggle is hidden where it's moot).
    const [viewMode, setViewMode] = useViewMode('jl_view', 'auto');
    const cardsEnforced = isBelowLg; // phones + portrait tablets
    const effectiveView =
        isMobile ? 'mobilecard'
        : cardsEnforced ? 'cards'
        : viewMode === 'table' ? 'table'
        : viewMode === 'cards' ? 'cards'
        : (isTablet ? 'cards' : 'table');

    const [showReleaseModal, setShowReleaseModal] = useState(false);
    const [csvData, setCsvData] = useState('');
    const [parsedPreview, setParsedPreview] = useState(null);
    const [releasing, setReleasing] = useState(false);
    const [releaseError, setReleaseError] = useState(null);
    const [releaseSuccess, setReleaseSuccess] = useState(null);
    const [cascadeStatus, setCascadeStatus] = useState(null); // null | 'recalculating' | 'done'
    const [printing, setPrinting] = useState(false);
    const cascadeTimeoutRef = useRef(null);

    const handleCascadeRecalculating = useCallback((isRecalculating) => {
        if (isRecalculating) {
            if (cascadeTimeoutRef.current) {
                clearTimeout(cascadeTimeoutRef.current);
                cascadeTimeoutRef.current = null;
            }
            setCascadeStatus('recalculating');
        } else {
            setCascadeStatus('done');
            cascadeTimeoutRef.current = setTimeout(() => {
                setCascadeStatus(null);
                cascadeTimeoutRef.current = null;
            }, 2000);
        }
    }, []);

    const [reviewMode, setReviewMode] = useState(
        () => localStorage.getItem('jl_reviewMode') === 'true'
    );
    const [isAdmin, setIsAdmin] = useState(false);
    const [isDrafter, setIsDrafter] = useState(false);
    const [canUseKatie, setCanUseKatie] = useState(false);
    const [isFilterMinimized, setIsFilterMinimized] = useState(() => {
        // Default minimal: collapse the big project-filter buttons on first load. Returning users keep their choice.
        const stored = localStorage.getItem('jl_minimized');
        return stored === null ? true : stored === 'true';
    });
    const [showArchiveModal, setShowArchiveModal] = useState(false);
    const [archivePreview, setArchivePreview] = useState(null);
    const [archiving, setArchiving] = useState(false);
    const [showRenumberModal, setShowRenumberModal] = useState(false);
    const [renumberPreview, setRenumberPreview] = useState(null);
    const [renumbering, setRenumbering] = useState(false);

    const {
        selectedProjectNames,
        search,
        setSelectedProjectNames,
        setSearch,
        projectNameOptions,
        projectOptions,
        stageToGroup,
        stageGroupColors,
        stageGroupDupColors,
        displayJobs,
        boardJobs,
        propagatedAsapJobs,
        secondarySearchResults,
        totalFabHrs,
        totalInstallHrs,
        resetFilters,
        selectedSubset,
        setSelectedSubset,
        columnFilters,
        columnSort,
        setColumnFilter,
        setColumnSort,
        matchesFilters,
        matchesSearch,
    } = useJobsFilters(jobs);

    // Active column-filter chips (mirrors Drafting WL) — one removable chip per selected value.
    const activeFilterChips = useMemo(
        () => JL_FILTER_CHIP_ORDER
            .filter((col) => (columnFilters[col]?.length ?? 0) > 0)
            .flatMap((col) => columnFilters[col].map((value) => ({
                column: col,
                value,
                label: JL_FILTER_LABELS[col] ?? col,
            }))),
        [columnFilters]
    );

    // Fetch user auth info to check admin status
    useEffect(() => {
        const fetchUserInfo = async () => {
            try {
                const user = await checkAuth();
                setIsAdmin(user?.is_admin || false);
                setIsDrafter(user?.is_drafter || false);
                setCanUseKatie(userCanAccessKatieFilter(user));
            } catch (err) {
                console.error('Error fetching user info:', err);
                setIsAdmin(false);
                setIsDrafter(false);
                setCanUseKatie(false);
            }
        };
        fetchUserInfo();
    }, []);

    // Persist filter panel + review state to localStorage
    useEffect(() => { localStorage.setItem('jl_minimized', isFilterMinimized); }, [isFilterMinimized]);
    useEffect(() => { localStorage.setItem('jl_reviewMode', reviewMode); }, [reviewMode]);

    // Delete job handler (passed to the table content)
    const handleDeleteJob = useCallback(async (row) => {
        try {
            await jobsApi.deleteJob(row['Job #'], row['Release #']);
            await refetch(true);
        } catch (error) {
            console.error('Failed to delete job:', error);
            throw error;
        }
    }, [refetch]);

    const formattedLastUpdated = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';

    const hasData = displayJobs.length > 0;
    const hasJobsData = !loading && jobs.length > 0;

    // Review-mode sort: PM (alphabetical) → Job # (asc) → compareSameJob tie-break.
    const reviewDisplayJobs = useMemo(
        () => (reviewMode ? reviewSort(displayJobs) : displayJobs),
        [displayJobs, reviewMode]
    );

    // On-screen render list: the in-filter jobs followed by the out-of-department ASAP
    // block (divider sentinel + propagated rows). The divider is assembled here, at the
    // render layer only, so it never leaks into counts/CSV/PDF that read displayJobs.
    const renderRows = useMemo(() => {
        if (propagatedAsapJobs.length === 0) return reviewDisplayJobs;
        return [
            ...reviewDisplayJobs,
            { id: '__asap_propagated_divider__', _asapDivider: true, _asapCount: propagatedAsapJobs.length },
            ...propagatedAsapJobs,
        ];
    }, [reviewDisplayJobs, propagatedAsapJobs]);

    // Compute fab_order values that appear on more than one release within the same
    // stage group (cross-group collisions aren't real conflicts). 80.555 is the
    // DEFAULT_FAB_ORDER sentinel; values < 3 are reserved fixed tiers — both excluded.
    const duplicateFabOrders = useMemo(() => {
        const countsByGroup = new Map();
        for (const row of reviewDisplayJobs) {
            const fo = row['Fab Order'];
            if (fo == null || fo < 3 || fo === 80.555) continue;
            const group = stageToGroup?.[row['Stage']] || 'FABRICATION';
            let counts = countsByGroup.get(group);
            if (!counts) {
                counts = new Map();
                countsByGroup.set(group, counts);
            }
            counts.set(fo, (counts.get(fo) || 0) + 1);
        }
        const dupesByGroup = new Map();
        for (const [group, counts] of countsByGroup) {
            const dupes = new Set();
            for (const [val, count] of counts) {
                if (count > 1) dupes.add(val);
            }
            if (dupes.size > 0) dupesByGroup.set(group, dupes);
        }
        return dupesByGroup;
    }, [reviewDisplayJobs, stageToGroup]);

    // Filter and order columns based on the defined order
    const columnHeaders = useMemo(
        () => columnOrder.filter(col => columns.includes(col)),
        [columns]
    );

    /**
     * Per-column reachable values: for each filterable column C, the set of unique
     * non-blank values present in jobs that pass every active filter except C's own
     * column filter (Excel-style narrowing). Also tracks whether blanks are reachable.
     */
    const uniqueValuesByColumn = useMemo(() => {
        // Table-only output: the Board never renders the column-header dropdowns,
        // so skip the O(columns × jobs) sweep entirely while it's unmounted. The
        // memo recomputes on the route flip back to the table.
        if (onBoardRoute) return {};
        const out = {};
        FILTERABLE_COLUMNS.forEach((col) => {
            const set = new Set();
            let hasBlanks = false;
            for (const job of jobs) {
                if (!matchesFilters(job)) continue;
                if (!matchesSearch(job, search)) continue;
                let ok = true;
                for (const k in columnFilters) {
                    if (k === col) continue;
                    const allowed = columnFilters[k];
                    if (!allowed || allowed.length === 0) continue;
                    const v = job[k];
                    const blank = (v === null || v === undefined || String(v).trim() === '');
                    if (blank ? !allowed.includes('(Blanks)') : !allowed.includes(String(v).trim())) {
                        ok = false;
                        break;
                    }
                }
                if (!ok) continue;
                const v = job[col];
                if (v === null || v === undefined || String(v).trim() === '') hasBlanks = true;
                else set.add(String(v).trim());
            }
            out[col] = {
                values: [...set].sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })),
                hasBlanks,
            };
        });
        return out;
    }, [onBoardRoute, jobs, columnFilters, matchesFilters, matchesSearch, search]);

    const jumpToTarget = useJumpToHighlight({
        loading,
        searchParams,
        mode: 'job-release',
    });

    // Normalize column width percentages so visible columns sum to 100%
    const columnWidthPercents = useMemo(() => {
        const defaultWeight = 5; // weight for columns not listed in COLUMN_WIDTH_PERCENT
        const total = columnHeaders.reduce((sum, col) => sum + (COLUMN_WIDTH_PERCENT[col] ?? defaultWeight), 0);
        return Object.fromEntries(
            columnHeaders.map((col) => {
                const weight = COLUMN_WIDTH_PERCENT[col] ?? defaultWeight;
                return [col, (weight / total) * 100];
            })
        );
    }, [columnHeaders]);

    const handleReleaseClick = () => {
        setShowReleaseModal(true);
        setCsvData('');
        setParsedPreview(null);
        setReleaseError(null);
        setReleaseSuccess(null);
    };

    const handleCloseModal = () => {
        setShowReleaseModal(false);
        setCsvData('');
        setParsedPreview(null);
        setReleaseError(null);
        setReleaseSuccess(null);
    };

    const parsePreviewData = (data) => {
        if (!data || !data.trim()) {
            setParsedPreview(null);
            return;
        }

        try {
            const firstLine = data.split('\n')[0];
            const delimiter = firstLine.includes('\t') ? '\t' : ',';

            const lines = data.split('\n').filter(line => line.trim());
            const expectedColumns = [
                'Job #', 'Release #', 'Job', 'Description', 'Fab Hrs',
                'Install HRS', 'Paint color', 'PM', 'BY', 'Released', 'Fab Order'
            ];

            let startIdx = 0;
            const firstRow = lines[0].split(delimiter);
            if (firstRow.length === expectedColumns.length) {
                const firstRowLower = firstRow.map(cell => cell.toLowerCase().trim());
                const hasHeaderKeywords = expectedColumns.some((col, idx) =>
                    col.toLowerCase().includes(firstRowLower[idx]) ||
                    firstRowLower[idx].includes(col.toLowerCase().split(' ')[0])
                );
                if (hasHeaderKeywords) {
                    startIdx = 1;
                }
            }

            const parsedRows = [];
            for (let i = startIdx; i < lines.length; i++) {
                const cells = lines[i].split(delimiter);
                if (cells.length === 0 || cells.every(cell => !cell.trim())) continue;

                while (cells.length < expectedColumns.length) {
                    cells.push('');
                }

                const row = {};
                expectedColumns.forEach((col, idx) => {
                    row[col] = cells[idx] ? cells[idx].trim() : '';
                });
                parsedRows.push(row);
            }

            setParsedPreview(parsedRows.length > 0 ? parsedRows : null);
        } catch (error) {
            console.error('Error parsing preview:', error);
            setParsedPreview(null);
        }
    };

    const handleCsvDataChange = (e) => {
        const value = e.target.value;
        setCsvData(value);
        parsePreviewData(value);
    };

    const handleReleaseSubmit = async () => {
        if (!csvData.trim()) {
            setReleaseError('Please paste CSV data');
            return;
        }

        setReleasing(true);
        setReleaseError(null);
        setReleaseSuccess(null);

        try {
            const result = await jobsApi.releaseJobData(csvData);
            setReleaseSuccess({
                processed: result.processed_count || 0,
                created: result.created_count || 0,
                updated: result.updated_count || 0,
                errors: result.error_count || 0,
                collisions: result.collisions || [],
                collision_count: result.collision_count || 0
            });

            setReleasing(false);

            if (result.created_count > 0) {
                fetchAll();
            }

            if (!result.collisions || result.collisions.length === 0) {
                setTimeout(() => {
                    handleCloseModal();
                }, 3000);
            }
        } catch (error) {
            setReleaseError(error.message || 'Failed to release job data');
            setReleasing(false);
        }
    };

    const handleExportCSV = () => {
        const exportColumns = columnHeaders.filter(col => col !== 'Urgency');
        const dateColumns = new Set(['Released', 'Start install', 'Comp. ETA', 'Job Comp', 'Invoiced']);

        const toIsoDate = (value) => {
            if (!value) return '';
            if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) {
                return value.split('T')[0];
            }
            const d = new Date(value);
            if (isNaN(d.getTime())) return '';
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${y}-${m}-${day}`;
        };

        const escapeCSV = (value) => {
            if (value === null || value === undefined) return '';
            const str = Array.isArray(value) ? value.join('; ') : String(value);
            if (/[",\r\n]/.test(str)) {
                return `"${str.replace(/"/g, '""')}"`;
            }
            return str;
        };

        const headerRow = exportColumns.map(escapeCSV).join(',');
        const dataRows = reviewDisplayJobs.map(row =>
            exportColumns.map(col => {
                let value = row[col];
                if (dateColumns.has(col)) value = toIsoDate(value);
                else if ((col === 'Fab Hrs' || col === 'Install HRS') && value != null && value !== '') {
                    const n = parseFloat(value);
                    if (!isNaN(n)) value = n.toFixed(2);
                }
                return escapeCSV(value);
            }).join(',')
        );

        const csv = [headerRow, ...dataRows].join('\r\n');
        const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const now = new Date();
        const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
        const a = document.createElement('a');
        a.href = url;
        a.download = `job-log-${stamp}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const handlePrint = async () => {
        if (printing) return;
        setPrinting(true);
        try {
            // Print always uses the review sort regardless of the on-screen toggle.
            // Sorted here, on demand, rather than in a memo that would re-run on
            // every filter/poll change for a rarely-used action.
            await generateJobLogReviewPdf({
                jobs: reviewSort(displayJobs),
                columnHeaders,
                columnWidthPercent: COLUMN_WIDTH_PERCENT,
            });
        } catch (err) {
            console.error('Failed to generate Job Log Review PDF', err);
            alert('Failed to generate PDF. See console for details.');
        } finally {
            setPrinting(false);
        }
    };

    // Everything the child content views (JobLogContent / PMBoardContent) need.
    const outletContext = useMemo(() => ({
        // dataset / status
        loading, fetchError, refetch,
        // filtered lists
        displayJobs, boardJobs, renderRows, secondarySearchResults,
        // filter outputs for the table column-header dropdowns
        search, selectedSubset,
        columnFilters, columnSort, setColumnFilter, setColumnSort, uniqueValuesByColumn,
        stageToGroup, stageGroupColors, stageGroupDupColors, duplicateFabOrders,
        // table column metadata
        columnHeaders, columnWidthPercents,
        // role / view / theme
        isAdmin, isDrafter, isOldMan, effectiveView, isDesktop, reviewMode, hasJobsData,
        // shared handlers
        handleDeleteJob, handleCascadeRecalculating, jumpToTarget,
    }), [
        loading, fetchError, refetch,
        displayJobs, boardJobs, renderRows, secondarySearchResults,
        search, selectedSubset,
        columnFilters, columnSort, setColumnFilter, setColumnSort, uniqueValuesByColumn,
        stageToGroup, stageGroupColors, stageGroupDupColors, duplicateFabOrders,
        columnHeaders, columnWidthPercents,
        isAdmin, isDrafter, isOldMan, effectiveView, isDesktop, reviewMode, hasJobsData,
        handleDeleteJob, handleCascadeRecalculating, jumpToTarget,
    ]);

    return (
        <>
            <div
                className="w-full h-[calc(100vh-3.5rem)] 3xl:h-[calc(100vh-4rem)] bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 py-2 px-2 3xl:py-4 3xl:px-6 flex flex-col"
                style={{
                    width: '100%',
                    minWidth: '100%',
                    paddingLeft: 'max(0.5rem, env(safe-area-inset-left))',
                    paddingRight: 'max(0.5rem, env(safe-area-inset-right))',
                    paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))',
                }}
            >
                <div className="max-w-full mx-auto w-full h-full flex flex-col" style={{ width: '100%' }}>
                    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col h-full">

                        <div className="p-2 flex flex-col flex-1 min-h-0 space-y-1.5">
                            <div className="bg-gray-100 dark:bg-slate-700 rounded-lg p-1.5 border border-gray-200 dark:border-slate-600 flex-shrink-0 space-y-1.5">

                                {/* Row 1: Project name buttons — only visible when expanded */}
                                {!isFilterMinimized && (
                                    <div
                                        className="grid gap-1"
                                        style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${isMobile ? 140 : 100}px, 1fr))` }}
                                    >
                                        <button
                                            onClick={() => setSelectedProjectNames([])}
                                            className={`w-full px-2.5 py-1 rounded text-xs font-medium transition-all ${selectedProjectNames.length === 0
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-200 dark:hover:bg-slate-500'
                                                }`}
                                            title="Clear the project filter and show releases from every project."
                                        >
                                            All
                                        </button>
                                        {projectNameOptions.map((option) => (
                                            <button
                                                key={option}
                                                onClick={() => {
                                                    setSelectedProjectNames(prev =>
                                                        prev.includes(option)
                                                            ? prev.filter(name => name !== option)
                                                            : [...prev, option]
                                                    );
                                                }}
                                                className={`w-full px-2.5 py-1 rounded text-xs font-medium transition-all ${selectedProjectNames.includes(option)
                                                    ? 'bg-blue-700 text-white'
                                                    : 'bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-200 dark:hover:bg-slate-500'
                                                    }`}
                                                title={`Toggle "${option}" — when selected, only releases from this project are shown. Select multiple to combine projects.`}
                                            >
                                                {option.length > 20 ? option.slice(0, 20) + '…' : option}
                                            </button>
                                        ))}
                                    </div>
                                )}

                                {/* Row 2: primary CTA + Actions/Projects + quick filters + view switcher + project chevron */}
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    {/* Table | Cards | Auto — how the Table view renders (left-aligned to mirror DWL);
                                        irrelevant on Board/Timeline and hidden below lg where card mode is enforced */}
                                    {!onBoardRoute && !cardsEnforced && (
                                        <ViewToggle value={viewMode} onChange={setViewMode} />
                                    )}

                                    <button
                                        onClick={handleReleaseClick}
                                        className="px-3 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap inline-flex items-center gap-1 bg-blue-700 text-white border border-blue-700 hover:bg-blue-800"
                                        title="Create new releases from a CSV paste"
                                    >
                                        <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d="M7 2v10M2 7h10" /></svg>New Release
                                    </button>

                                    <Dropdown label="Actions">
                                        <DropdownItem onClick={handlePrint} disabled={!hasData || loading || !reviewMode || printing}>
                                            {printing ? '⏳ Building…' : '🖨️ Print'}
                                        </DropdownItem>
                                        <DropdownItem onClick={() => navigate('/archive')}>🗄️ Archive</DropdownItem>
                                        {isAdmin && (
                                            <DropdownItem onClick={handleExportCSV} disabled={!hasData || loading}>⬇️ Export CSV</DropdownItem>
                                        )}
                                        {isAdmin && (
                                            <DropdownItem onClick={async () => {
                                                try {
                                                    const data = await jobsApi.getArchivePreview();
                                                    setArchivePreview(data);
                                                    setShowArchiveModal(true);
                                                } catch (err) {
                                                    alert(`Failed to load archive preview: ${err.message}`);
                                                }
                                            }}>📦 Send to Archive</DropdownItem>
                                        )}
                                        {isAdmin && (
                                            <DropdownItem onClick={async () => {
                                                try {
                                                    const data = await jobsApi.renumberFabricationFabOrders({ dryRun: true });
                                                    setRenumberPreview(data);
                                                    setShowRenumberModal(true);
                                                } catch (err) {
                                                    alert(`Failed to load renumber preview: ${err.message}`);
                                                }
                                            }}>🔢 Renumber Fab Order</DropdownItem>
                                        )}
                                    </Dropdown>

                                    {/* Projects filter (number + name) — separate from the column-header dropdowns */}
                                    <ProjectFilterDropdown
                                        options={projectOptions}
                                        selected={selectedProjectNames}
                                        onChange={setSelectedProjectNames}
                                    />

                                    {/* Stage quick filters — linear buttons on desktop, single dropdown on tablet/mobile */}
                                    <JobLogQuickFilters
                                        selectedSubset={selectedSubset}
                                        setSelectedSubset={setSelectedSubset}
                                        reviewMode={reviewMode}
                                        setReviewMode={setReviewMode}
                                        compact={isMobile || isTablet}
                                        canUseKatie={canUseKatie}
                                    />

                                    <div className="flex-1" />

                                    {/* Table | Board | Timeline — instant view switching over the shared releases dataset */}
                                    <ReleasesViewSwitcher />

                                    {/* Project filter buttons — discreet chevron toggle, collapsed by default */}
                                    <button
                                        onClick={() => setIsFilterMinimized(!isFilterMinimized)}
                                        className="p-1.5 rounded-lg hover:bg-gray-300 dark:hover:bg-slate-600 transition-colors flex-shrink-0"
                                        title={isFilterMinimized ? "Show project filter buttons" : "Hide project filter buttons"}
                                    >
                                        <span className="text-xl leading-none text-gray-600 dark:text-slate-300">{isFilterMinimized ? '▾' : '▴'}</span>
                                    </button>
                                </div>

                                {/* Active-filter chips — only renders when at least one filter is active */}
                                <ActiveFilterChips
                                    search={search}
                                    selectedSubset={selectedSubset}
                                    reviewMode={reviewMode}
                                    selectedProjectNames={selectedProjectNames}
                                    columnFilters={columnFilters}
                                    columnSort={columnSort}
                                    onClearSearch={() => setSearch('')}
                                    onClearSubset={() => setSelectedSubset(null)}
                                    onClearReview={() => setReviewMode(false)}
                                    onRemoveProject={(name) => setSelectedProjectNames(prev => prev.filter(n => n !== name))}
                                    onClearColumnFilter={(col) => setColumnFilter(col, [])}
                                    onClearSort={() => setColumnSort(null)}
                                />

                                {/* Row 3: Search + stats — always visible */}
                                <div className="flex items-center justify-between gap-1.5 flex-wrap">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                        <div className="flex items-center gap-1.5">
                                            <label className="text-xs font-semibold text-gray-700 dark:text-slate-200 whitespace-nowrap">
                                                Search:
                                            </label>
                                            <input
                                                type="text"
                                                value={search}
                                                onChange={(e) => setSearch(e.target.value)}
                                                placeholder="Job #, release, name, description..."
                                                title="Live-filter the visible rows by Job #, Release #, project name, or description. Case-insensitive substring match."
                                                className="w-48 sm:w-64 px-2 py-2 md:py-0.5 text-sm md:text-xs border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-600 text-gray-900 dark:text-slate-100"
                                            />
                                        </div>
                                        <button
                                            onClick={() => { resetFilters(); setReviewMode(false); }}
                                            className="text-sm text-blue-600 dark:text-blue-400 underline hover:no-underline whitespace-nowrap"
                                            title="Clear project selections, stage subset, Review mode, and the search box to return to the default view."
                                        >
                                            Reset Filters
                                        </button>
                                    </div>
                                    <div className="flex items-center gap-3 text-sm font-semibold text-gray-700 dark:text-slate-200">
                                        <span>
                                            {/* Board ignores column-header filters, so its count comes from boardJobs */}
                                            Total: <span className="text-gray-900 dark:text-slate-100 font-bold">{onBoardRoute ? boardJobs.length : displayJobs.length}</span> records
                                        </span>
                                        <span className="text-gray-300 dark:text-slate-500">|</span>
                                        <span>
                                            Fab HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{totalFabHrs.toFixed(2)}</span>
                                        </span>
                                        <span className="text-gray-300 dark:text-slate-500">|</span>
                                        <span>
                                            Install HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{totalInstallHrs.toFixed(2)}</span>
                                        </span>
                                        <span className="text-gray-300 dark:text-slate-500">|</span>
                                        <span className="text-gray-500 dark:text-slate-400 font-normal">
                                            Last updated: <span className="font-semibold text-gray-700 dark:text-slate-200">{formattedLastUpdated}</span>
                                        </span>
                                    </div>
                                </div>

                                {/* Active filter chips */}
                                {activeFilterChips.length > 0 && (
                                    <div className="flex items-center gap-1.5 flex-wrap border-t border-gray-200 dark:border-slate-600 pt-2">
                                        <span className="text-xs font-semibold text-gray-500 dark:text-slate-400 whitespace-nowrap">Active filters:</span>
                                        {activeFilterChips.map((chip) => (
                                            <span
                                                key={`${chip.column}:${chip.value}`}
                                                className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 text-blue-700 dark:text-blue-300 text-xs font-medium"
                                            >
                                                <span className="whitespace-nowrap">{chip.label}: {chip.value}</span>
                                                <button
                                                    type="button"
                                                    onClick={() => setColumnFilter(chip.column, (columnFilters[chip.column] ?? []).filter((v) => v !== chip.value))}
                                                    className="flex items-center justify-center w-4 h-4 rounded-full leading-none text-blue-500 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-800 hover:text-blue-800 dark:hover:text-blue-100 transition-colors"
                                                    aria-label={`Remove ${chip.label} filter ${chip.value}`}
                                                    title={`Remove ${chip.label}: ${chip.value}`}
                                                >
                                                    ×
                                                </button>
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Active view content (Table / Board / Timeline) */}
                            <Outlet context={outletContext} />
                        </div>
                    </div>
                </div>

                {/* Archive Modal */}
                {showArchiveModal && archivePreview && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-3xl w-full mx-4 max-h-[90vh] flex flex-col">
                            <div className="bg-gradient-to-r from-amber-500 to-amber-600 px-6 py-4 rounded-t-xl">
                                <div className="flex items-center justify-between">
                                    <h2 className="text-2xl font-bold text-white">Send to Archive</h2>
                                    <button
                                        onClick={() => setShowArchiveModal(false)}
                                        className="text-white hover:text-gray-200 text-2xl font-bold"
                                        disabled={archiving}
                                    >
                                        ×
                                    </button>
                                </div>
                            </div>
                            <div className="p-6 overflow-y-auto flex-1">
                                {archivePreview.count === 0 ? (
                                    <p className="text-gray-600 dark:text-slate-300">No releases are eligible for archival. Releases need both Job Comp and Invoiced set to &apos;X&apos;.</p>
                                ) : (
                                    <>
                                        <p className="mb-4 text-sm text-gray-700 dark:text-slate-300">
                                            <strong>{archivePreview.count}</strong> release{archivePreview.count !== 1 ? 's' : ''} will be moved to the archive:
                                        </p>
                                        <div className="max-h-64 overflow-y-auto border border-gray-200 dark:border-slate-600 rounded">
                                            <table className="w-full text-xs">
                                                <thead className="bg-gray-100 dark:bg-slate-700 sticky top-0">
                                                    <tr>
                                                        <th className="px-2 py-1 text-left">Job #</th>
                                                        <th className="px-2 py-1 text-left">Release</th>
                                                        <th className="px-2 py-1 text-left">Name</th>
                                                        <th className="px-2 py-1 text-left">Description</th>
                                                        <th className="px-2 py-1 text-left">Stage</th>
                                                        <th className="px-2 py-1 text-left">Job Comp (Install Prog)</th>
                                                        <th className="px-2 py-1 text-left">Invoiced</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {archivePreview.releases.map((r, i) => (
                                                        <tr key={`${r.job}-${r.release}`} className={i % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-gray-50 dark:bg-slate-750'}>
                                                            <td className="px-2 py-1">{r.job}</td>
                                                            <td className="px-2 py-1">{r.release}</td>
                                                            <td className="px-2 py-1">{r.job_name}</td>
                                                            <td className="px-2 py-1">{r.description}</td>
                                                            <td className="px-2 py-1">{r.stage}</td>
                                                            <td className="px-2 py-1">{r.job_comp}</td>
                                                            <td className="px-2 py-1">{r.invoiced}</td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </>
                                )}
                            </div>
                            <div className="px-6 py-4 border-t border-gray-200 dark:border-slate-600 flex justify-end gap-3">
                                <button
                                    onClick={() => setShowArchiveModal(false)}
                                    className="px-4 py-2 rounded text-sm font-medium bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-200 hover:bg-gray-200 dark:hover:bg-slate-600"
                                    disabled={archiving}
                                >
                                    Cancel
                                </button>
                                {archivePreview.count > 0 && (
                                    <button
                                        onClick={async () => {
                                            setArchiving(true);
                                            try {
                                                const result = await jobsApi.confirmArchive();
                                                setShowArchiveModal(false);
                                                setArchivePreview(null);
                                                await refetch(true);
                                                alert(`Successfully archived ${result.count} release${result.count !== 1 ? 's' : ''}.`);
                                            } catch (err) {
                                                alert(`Failed to archive: ${err.message}`);
                                            } finally {
                                                setArchiving(false);
                                            }
                                        }}
                                        disabled={archiving}
                                        className="px-4 py-2 rounded text-sm font-medium bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        {archiving ? 'Archiving...' : `Confirm Archive (${archivePreview.count})`}
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {/* Renumber Fab Order Modal */}
                {showRenumberModal && renumberPreview && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-3xl w-full mx-4 max-h-[90vh] flex flex-col">
                            <div className="bg-gradient-to-r from-amber-500 to-amber-600 px-6 py-4 rounded-t-xl">
                                <div className="flex items-center justify-between">
                                    <h2 className="text-2xl font-bold text-white">Renumber Fab Order</h2>
                                    <button
                                        onClick={() => setShowRenumberModal(false)}
                                        className="text-white hover:text-gray-200 text-2xl font-bold"
                                        disabled={renumbering}
                                    >
                                        ×
                                    </button>
                                </div>
                            </div>
                            <div className="p-6 overflow-y-auto flex-1">
                                <p className="mb-3 text-sm text-gray-700 dark:text-slate-300">
                                    Compresses FABRICATION group <code>fab_order</code> values to a contiguous block starting at <strong>3</strong>, preserving the current relative order. Welded QC, Paint Start, and later stages are untouched.
                                </p>
                                <div className="mb-4 grid grid-cols-4 gap-3 text-sm">
                                    <div className="bg-gray-50 dark:bg-slate-700 rounded p-2">
                                        <div className="text-xs text-gray-500 dark:text-slate-400">FAB total</div>
                                        <div className="text-lg font-bold">{renumberPreview.total_fabrication}</div>
                                    </div>
                                    <div className="bg-amber-50 dark:bg-amber-900/30 rounded p-2">
                                        <div className="text-xs text-gray-500 dark:text-slate-400">Will change</div>
                                        <div className="text-lg font-bold text-amber-700 dark:text-amber-300">{renumberPreview.changed}</div>
                                    </div>
                                    <div className="bg-gray-50 dark:bg-slate-700 rounded p-2">
                                        <div className="text-xs text-gray-500 dark:text-slate-400">Unchanged</div>
                                        <div className="text-lg font-bold">{renumberPreview.unchanged}</div>
                                    </div>
                                    <div className="bg-gray-50 dark:bg-slate-700 rounded p-2" title="Releases at the 80.555 placeholder are preserved as-is.">
                                        <div className="text-xs text-gray-500 dark:text-slate-400">Placeholder (80.555)</div>
                                        <div className="text-lg font-bold">{renumberPreview.placeholder_preserved ?? 0}</div>
                                    </div>
                                </div>
                                {renumberPreview.changed === 0 ? (
                                    <p className="text-gray-600 dark:text-slate-300">Nothing to do — fab_orders are already compressed.</p>
                                ) : (
                                    <div className="max-h-64 overflow-y-auto border border-gray-200 dark:border-slate-600 rounded">
                                        <table className="w-full text-xs">
                                            <thead className="bg-gray-100 dark:bg-slate-700 sticky top-0">
                                                <tr>
                                                    <th className="px-2 py-1 text-left">Job-Release</th>
                                                    <th className="px-2 py-1 text-left">Stage</th>
                                                    <th className="px-2 py-1 text-right">From</th>
                                                    <th className="px-2 py-1 text-right">→</th>
                                                    <th className="px-2 py-1 text-right">To</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {renumberPreview.changes.map((c, i) => (
                                                    <tr key={`${c.job}-${c.release}`} className={`${c.changed === false ? 'opacity-60' : ''} ${i % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-gray-50 dark:bg-slate-750'}`}>
                                                        <td className="px-2 py-1 font-mono">{c.job}-{c.release}</td>
                                                        <td className="px-2 py-1">{c.stage}</td>
                                                        <td className="px-2 py-1 text-right text-gray-500">{c.from ?? '—'}</td>
                                                        <td className="px-2 py-1 text-right text-gray-400">→</td>
                                                        <td className={`px-2 py-1 text-right ${c.changed === false ? 'text-gray-500' : 'font-bold'}`}>{c.to}{c.changed === false ? ' (no change)' : ''}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>
                            <div className="px-6 py-4 border-t border-gray-200 dark:border-slate-600 flex justify-end gap-3">
                                <button
                                    onClick={() => setShowRenumberModal(false)}
                                    className="px-4 py-2 rounded text-sm font-medium bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-200 hover:bg-gray-200 dark:hover:bg-slate-600"
                                    disabled={renumbering}
                                >
                                    Cancel
                                </button>
                                {renumberPreview.changed > 0 && (
                                    <button
                                        onClick={async () => {
                                            setRenumbering(true);
                                            try {
                                                const result = await jobsApi.renumberFabricationFabOrders({ dryRun: false });
                                                setShowRenumberModal(false);
                                                setRenumberPreview(null);
                                                await refetch(true);
                                                alert(`Renumbered ${result.changed} release${result.changed !== 1 ? 's' : ''}.`);
                                            } catch (err) {
                                                alert(`Failed to renumber: ${err.message}`);
                                            } finally {
                                                setRenumbering(false);
                                            }
                                        }}
                                        disabled={renumbering}
                                        className="px-4 py-2 rounded text-sm font-medium bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        {renumbering ? 'Renumbering...' : `Apply (${renumberPreview.changed})`}
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {/* Release Modal */}
                {showReleaseModal && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-3xl w-full mx-4 max-h-[90vh] flex flex-col">
                            <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                                <div className="flex items-center justify-between">
                                    <h2 className="text-2xl font-bold text-white">Release Job Data</h2>
                                    <button
                                        onClick={handleCloseModal}
                                        className="text-white hover:text-gray-200 dark:hover:text-slate-200 text-2xl font-bold"
                                        disabled={releasing}
                                    >
                                        ×
                                    </button>
                                </div>
                            </div>

                            <div className="p-6 flex-1 overflow-y-auto">
                                <div className="mb-4">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                        Paste Data (CSV or tab-separated from Google Sheets)
                                    </label>
                                    <p className="text-xs text-gray-600 dark:text-slate-400 mb-2">
                                        Expected columns: Job #, Release #, Job, Description, Fab Hrs, Install HRS, Paint color, PM, BY, Released, Fab Order
                                    </p>
                                    <textarea
                                        value={csvData}
                                        onChange={handleCsvDataChange}
                                        placeholder="Paste data here (supports CSV or tab-separated from Google Sheets)..."
                                        className="w-full h-64 px-3 py-2 border border-gray-300 dark:border-slate-500 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 font-mono text-sm bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                                        disabled={releasing}
                                    />
                                </div>

                                {/* Preview Table */}
                                {parsedPreview && parsedPreview.length > 0 && (
                                    <div className="mb-4">
                                        <h3 className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                            Preview ({parsedPreview.length} row{parsedPreview.length !== 1 ? 's' : ''})
                                        </h3>
                                        <div className="border border-gray-400 dark:border-slate-700 rounded-lg overflow-hidden">
                                            <div className="overflow-x-auto max-h-96">
                                                <table className="w-full text-xs border-collapse">
                                                    <thead className="bg-gray-100 dark:bg-slate-700 sticky top-0">
                                                        <tr>
                                                            {['Job #', 'Release #', 'Job', 'Description', 'Fab Hrs', 'Install HRS', 'Paint color', 'PM', 'BY', 'Released', 'Fab Order'].map((col) => (
                                                                <th
                                                                    key={col}
                                                                    className="px-2 py-1.5 text-left font-semibold text-gray-700 dark:text-slate-200 border-b border-gray-400 dark:border-slate-700 whitespace-nowrap"
                                                                >
                                                                    {col}
                                                                </th>
                                                            ))}
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {parsedPreview.map((row, idx) => (
                                                            <tr key={idx} className={idx % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-gray-50 dark:bg-slate-700'}>
                                                                {['Job #', 'Release #', 'Job', 'Description', 'Fab Hrs', 'Install HRS', 'Paint color', 'PM', 'BY', 'Released', 'Fab Order'].map((col) => (
                                                                    <td
                                                                        key={col}
                                                                        className="px-2 py-1.5 border-b border-gray-200 dark:border-slate-600 text-gray-900 dark:text-slate-100 whitespace-nowrap"
                                                                    >
                                                                        {row[col] || <span className="text-gray-400 dark:text-slate-500">—</span>}
                                                                    </td>
                                                                ))}
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {releaseError && (
                                    <div className="mb-4 bg-red-50 dark:bg-red-900/30 border-l-4 border-red-500 text-red-700 dark:text-red-200 px-4 py-3 rounded">
                                        <p className="font-semibold">Error</p>
                                        <p className="text-sm">{releaseError}</p>
                                    </div>
                                )}

                                {releaseSuccess && releaseSuccess.created > 0 && (
                                    <div className="mb-4 bg-green-50 dark:bg-green-900/30 border-l-4 border-green-500 text-green-700 dark:text-green-200 px-4 py-3 rounded">
                                        <p className="font-semibold">Success!</p>
                                        <p className="text-sm">
                                            Created: {releaseSuccess.created}
                                            {releaseSuccess.errors > 0 && ` | Errors: ${releaseSuccess.errors}`}
                                        </p>
                                    </div>
                                )}

                                {releaseSuccess && releaseSuccess.collisions && releaseSuccess.collisions.length > 0 && (
                                    <div className="mb-4 bg-red-50 dark:bg-red-900/30 border-l-4 border-red-500 text-red-700 dark:text-red-200 px-4 py-3 rounded">
                                        <p className="font-semibold">Duplicate Releases</p>
                                        <ul className="text-sm mt-2 space-y-1">
                                            {releaseSuccess.collisions.map((col, idx) => (
                                                <li key={idx}>
                                                    <span className="font-medium">{col.job}-{col.release}</span> ({col.job_name}) already exists.
                                                    {col.suggested_next && (
                                                        <span> Try <span className="font-semibold">{col.job}-{col.suggested_next}</span></span>
                                                    )}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>

                            <div className="px-6 py-4 bg-gray-50 dark:bg-slate-700 rounded-b-xl flex justify-end gap-3">
                                <button
                                    onClick={handleCloseModal}
                                    className="px-4 py-2 bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 rounded-lg font-medium hover:bg-gray-50 dark:hover:bg-slate-500 transition-all"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleReleaseSubmit}
                                    disabled={releasing || !csvData.trim()}
                                    className={`px-4 py-2 rounded-lg font-medium transition-all ${releasing || !csvData.trim()
                                        ? 'bg-gray-300 dark:bg-slate-600 text-gray-500 dark:text-slate-400 cursor-not-allowed'
                                        : 'bg-accent-500 text-white hover:bg-accent-600'
                                        }`}
                                >
                                    {releasing ? (
                                        <>
                                            <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
                                            Releasing...
                                        </>
                                    ) : (
                                        'Release'
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {cascadeStatus && (
                    <div className={`fixed bottom-6 right-6 z-50 bg-white dark:bg-slate-800 border rounded-xl shadow-lg px-5 py-3 flex items-center gap-3 ${
                        cascadeStatus === 'done'
                            ? 'border-green-300 dark:border-green-600 animate-fade-out'
                            : 'border-gray-200 dark:border-slate-600 animate-fade-in'
                    }`}>
                        {cascadeStatus === 'recalculating' ? (
                            <>
                                <span className="inline-block animate-spin rounded-full h-5 w-5 border-2 border-accent-500 border-t-transparent"></span>
                                <span className="text-sm font-medium text-gray-700 dark:text-slate-200">Recalculating start install dates...</span>
                            </>
                        ) : (
                            <>
                                <svg className="h-5 w-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                </svg>
                                <span className="text-sm font-medium text-green-700 dark:text-green-400">Start install dates updated</span>
                            </>
                        )}
                    </div>
                )}

            </div>
        </>
    );
}

export default ReleasesLayout;
