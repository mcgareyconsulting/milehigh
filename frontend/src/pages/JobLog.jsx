/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Main job log page where users view, filter, reorder, and edit active job releases synced from Trello and Excel.
 * exports:
 *   JobLog: Page component with filterable job table, drag-and-drop row reordering, CSV release import, and jump-to-highlight support
 * imports_from: [react, react-router-dom, ../hooks/useJumpToHighlight, ../hooks/useJobsDataFetching, ../hooks/useJobsFilters, ../hooks/useJobsDragAndDrop, ../components/JobsTableRow, ../services/jobsApi]
 * imported_by: [App.jsx]
 * invariants:
 *   - Admin-only actions: drag reorder, CSV release import, archive
 *   - Jump-to highlight param triggers fetchAll to load every row regardless of filter
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React, { useMemo, useEffect, useState, useCallback, useRef } from 'react';
import { useTheme } from '../context/ThemeContext';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useJumpToHighlight } from '../hooks/useJumpToHighlight';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import { useJobsFilters } from '../hooks/useJobsFilters';
import ColumnHeaderFilter from '../components/ColumnHeaderFilter';
import { useJobsDragAndDrop } from '../hooks/useJobsDragAndDrop';
import { JobsTableRow } from '../components/JobsTableRow';
import { jobsApi } from '../services/jobsApi';
import { checkAuth } from '../utils/auth';

function JobLog() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { jobs, columns, loading, error: fetchError, lastUpdated, refetch, fetchAll } = useJobsDataFetching();
    const [showReleaseModal, setShowReleaseModal] = useState(false);
    const [csvData, setCsvData] = useState('');
    const [parsedPreview, setParsedPreview] = useState(null);
    const [releasing, setReleasing] = useState(false);
    const [releaseError, setReleaseError] = useState(null);
    const [releaseSuccess, setReleaseSuccess] = useState(null);
    const [cascadeStatus, setCascadeStatus] = useState(null); // null | 'recalculating' | 'done'
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
    const { isOldMan } = useTheme();
    const [reviewMode, setReviewMode] = useState(
        () => localStorage.getItem('jl_reviewMode') === 'true'
    );
    const [isAdmin, setIsAdmin] = useState(false);
    const [isFilterMinimized, setIsFilterMinimized] = useState(
        () => localStorage.getItem('jl_minimized') === 'true'
    );
    const [showArchiveModal, setShowArchiveModal] = useState(false);
    const [archivePreview, setArchivePreview] = useState(null);
    const [archiving, setArchiving] = useState(false);
    const [showRenumberModal, setShowRenumberModal] = useState(false);
    const [renumberPreview, setRenumberPreview] = useState(null);
    const [renumbering, setRenumbering] = useState(false);
    const tableScrollRef = useRef(null);

    // Use the filters hook
    const {
        selectedProjectNames,
        selectedStages,
        search,
        setSelectedProjectNames,
        setSelectedStages,
        setSearch,
        projectNameOptions,
        stageOptions,
        stageColors,
        stageToGroup,
        stageGroupColors,
        stageGroupDupColors,
        displayJobs,
        secondarySearchResults,
        totalFabHrs,
        totalInstallHrs,
        resetFilters,
        toggleStage,
        selectedSubset,
        setSelectedSubset,
        columnFilters,
        columnSort,
        setColumnFilter,
        setColumnSort,
        matchesFilters,
        matchesSearch,
    } = useJobsFilters(jobs);

    // Fetch user auth info to check admin status
    useEffect(() => {
        const fetchUserInfo = async () => {
            try {
                const user = await checkAuth();
                setIsAdmin(user?.is_admin || false);
            } catch (err) {
                console.error('Error fetching user info:', err);
                setIsAdmin(false);
            }
        };
        fetchUserInfo();
    }, []);

    // Persist filter panel state to localStorage
    useEffect(() => { localStorage.setItem('jl_minimized', isFilterMinimized); }, [isFilterMinimized]);
    useEffect(() => { localStorage.setItem('jl_reviewMode', reviewMode); }, [reviewMode]);

    // Update fab order handler (refetch after update to show collision detection changes)
    const updateFabOrder = useCallback(async (job, release, fabOrder) => {
        try {
            await jobsApi.updateFabOrder(job, release, fabOrder);
            // Refetch immediately to show collision detection changes and latest state
            await refetch(true);
        } catch (error) {
            // Error is already handled in the component, just rethrow
            throw error;
        }
    }, [refetch]);

    // Delete job handler
    const handleDeleteJob = useCallback(async (row) => {
        try {
            await jobsApi.deleteJob(row['Job #'], row['Release #']);
            // Refetch to remove the deleted row from the table
            await refetch(true);
        } catch (error) {
            console.error('Failed to delete job:', error);
            throw error;
        }
    }, [refetch]);

    // Drag and drop functionality (disabled for now)
    // const {
    //     draggedIndex,
    //     dragOverIndex,
    //     handleDragStart,
    //     handleDragOver,
    //     handleDragLeave,
    //     handleDrop,
    // } = useJobsDragAndDrop(jobs, displayJobs, updateFabOrder, selectedSubset);

    // Disabled drag and drop - set to null/empty handlers
    const draggedIndex = null;
    const dragOverIndex = null;
    const handleDragStart = () => { };
    const handleDragOver = () => { };
    const handleDragLeave = () => { };
    const handleDrop = () => { };

    const formatDate = (dateValue) => {
        if (!dateValue) return '—';
        try {
            // Handle ISO date strings (YYYY-MM-DD) - parse directly to avoid timezone issues
            if (typeof dateValue === 'string' && /^\d{4}-\d{2}-\d{2}/.test(dateValue)) {
                // Extract date parts directly from ISO string to avoid timezone conversion
                const parts = dateValue.split('T')[0].split('-');
                if (parts.length === 3) {
                    const year = parts[0];
                    const month = parts[1];
                    const day = parts[2];
                    // Return in MM/DD/YY format
                    return `${month}/${day}/${year.slice(-2)}`;
                }
            }
            // Fallback to Date object parsing for other formats
            const date = new Date(dateValue);
            if (isNaN(date.getTime())) return '—';
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const year = String(date.getFullYear()).slice(-2);
            return `${month}/${day}/${year}`;
        } catch (e) {
            return '—';
        }
    };

    const formatCellValue = (value, columnName) => {
        if (value === null || value === undefined || value === '') {
            return '—';
        }
        if (Array.isArray(value)) {
            return value.join(', ');
        }
        // Format Fab Hrs and Install HRS to 2 decimal places
        if (columnName === 'Fab Hrs' || columnName === 'Install HRS') {
            const numValue = parseFloat(value);
            if (!isNaN(numValue)) {
                return numValue.toFixed(2);
            }
        }
        return value;
    };

    const formattedLastUpdated = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';

    // Check if we have data to display
    // Only show "No records found" if we've finished loading and have no jobs at all
    // If we have jobs but displayJobs is empty, that means filters are excluding everything
    const hasData = displayJobs.length > 0;
    const hasJobsData = !loading && jobs.length > 0;

    // Stage completeness order (index 0 = least complete, higher = more complete)
    const STAGE_COMPLETENESS = {
        'Released': 0, 'Material Ordered': 1, 'Cut start': 2, 'Cut Complete': 3,
        'Fitup Start': 4, 'Fit Up Complete.': 5, 'Weld Start': 6, 'Weld Complete': 7,
        'Welded QC': 9, 'Paint Start': 10, 'Paint complete': 11,
        'Store at MHMW for shipping': 12, 'Shipping planning': 13,
        'Shipping completed': 14, 'Complete': 15,
    };

    // Defensive Complete check — tolerates whitespace + case drift in the stage value.
    // Otherwise STAGE_COMPLETENESS['Complete']=15 (highest) would push these rows to
    // the top of the descending sort instead of the bottom.
    const isCompleteStage = (stage) =>
        (stage || '').toString().trim().toLowerCase() === 'complete';

    const SHIP_COMPLETE_STAGE = 'Shipping completed';

    // 'X' = installed (highest); percent strings rank by their numeric value;
    // missing/blank ranks lowest so it sorts to the bottom of the ship-complete group.
    const installProgRank = (val) => {
        if (val == null) return -1;
        const s = val.toString().trim();
        if (s === '') return -1;
        if (s.toLowerCase() === 'x') return 101;
        const n = parseFloat(s);
        return Number.isFinite(n) ? n : -1;
    };

    // Tie-break for two rows that share the same PM + Job #.
    const compareSameJob = (a, b) => {
        const ca = isCompleteStage(a['Stage']);
        const cb = isCompleteStage(b['Stage']);
        if (ca !== cb) return ca ? 1 : -1;

        const sa = STAGE_COMPLETENESS[a['Stage']] ?? -1;
        const sb = STAGE_COMPLETENESS[b['Stage']] ?? -1;
        if (sa !== sb) return sb - sa;

        if (a['Stage'] === SHIP_COMPLETE_STAGE) {
            return installProgRank(b['Job Comp']) - installProgRank(a['Job Comp']);
        }
        const foA = a['Fab Order'] ?? Number.POSITIVE_INFINITY;
        const foB = b['Fab Order'] ?? Number.POSITIVE_INFINITY;
        return foA - foB;
    };

    // When Review mode is enabled, sort independently of other sort behavior:
    // 1) group by PM (no intermixing of PMs), PM groups ordered alphabetically,
    // 2) within each PM, sort by Project # ascending,
    // 3) within each Project #, sort by stage completeness (most complete first).
    const reviewDisplayJobs = useMemo(() => {
        if (!reviewMode) return displayJobs;

        const sorted = [...displayJobs];
        sorted.sort((a, b) => {
            const pmKeyA = (a['PM'] || 'No PM').toString();
            const pmKeyB = (b['PM'] || 'No PM').toString();

            // Different PMs: alphabetical by PM name (case-insensitive)
            if (pmKeyA !== pmKeyB) {
                return pmKeyA.toLowerCase().localeCompare(pmKeyB.toLowerCase());
            }

            // Same PM: sort by Project # (Job #) ascending
            const jobA = a['Job #'] || 0;
            const jobB = b['Job #'] || 0;
            if (jobA !== jobB) return jobA - jobB;

            return compareSameJob(a, b);
        });

        return sorted;
    }, [displayJobs, reviewMode]);

    // Compute fab_order values that appear on more than one release *within the same
    // stage group*. The client uses Welded QC (READY_TO_SHIP) for paint-sequence
    // ordering, so its numbering naturally collides with FABRICATION numbering — those
    // cross-group collisions are not real conflicts. 80.555 is the DEFAULT_FAB_ORDER
    // sentinel and values < 3 are reserved fixed tiers; both are excluded. The
    // FABRICATION dynamic block starts at 3, so ties at 3+ are real collisions.
    // Returns Map<groupKey, Set<number>> keyed by stage group.
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

    // Define column order explicitly
    const columnOrder = [
        'Job #',
        'Release #',
        'Job',
        'Description',
        'Fab Hrs',
        'Install HRS',
        'Paint color',
        'PM',
        'BY',
        'Released',
        'Fab Order',
        'Stage',
        'Urgency',
        'Start install',
        'Comp. ETA',
        'Job Comp',
        'Invoiced',
        'Notes'
    ];

    /**
     * Job log column widths as percentage of table width. Tune these to taste; they are
     * normalized so visible columns always sum to 100%. Only columns listed here get
     * custom widths; others share the remainder equally.
     */
    const COLUMN_WIDTH_PERCENT = {
        'Job #': 3,
        'Release #': 3,
        'Job': 6,
        'Description': 7,
        'Fab Hrs': 4,
        'Install HRS': 5,
        'Paint color': 6,
        'PM': 3,
        'BY': 3,
        'Released': 5,
        'Fab Order': 6,
        'Stage': 9,
        'Urgency': 7,
        'Start install': 5,
        'Comp. ETA': 5,
        'Job Comp': 5,
        'Invoiced': 5,
        'Notes': 10,
        'Actions': 5,
    };

    // Filter and order columns based on defined order
    const columnHeaders = useMemo(() => {
        // Only include columns that exist in the data and are in our defined order
        return columnOrder.filter(col => columns.includes(col) || col === 'Urgency');
    }, [columns]);

    // Phase 1 columns that get an Excel-style header dropdown filter.
    const FILTERABLE_COLUMNS = useMemo(() => new Set([
        'Job #', 'Release #', 'Job', 'Stage', 'Fab Order',
        'Paint color', 'Job Comp', 'Invoiced', 'PM', 'BY',
    ]), []);

    /**
     * Per-column reachable values: for each filterable column C, the set of unique
     * non-blank values present in jobs that pass every active filter except C's own
     * column filter (Excel-style narrowing). Also tracks whether blanks are reachable.
     */
    const uniqueValuesByColumn = useMemo(() => {
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
    }, [jobs, columnFilters, matchesFilters, matchesSearch, search, FILTERABLE_COLUMNS]);

    const tableColumnCount = columnHeaders.length;

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
            // Detect delimiter
            const firstLine = data.split('\n')[0];
            const delimiter = firstLine.includes('\t') ? '\t' : ',';

            // Parse rows
            const lines = data.split('\n').filter(line => line.trim());
            const expectedColumns = [
                'Job #', 'Release #', 'Job', 'Description', 'Fab Hrs',
                'Install HRS', 'Paint color', 'PM', 'BY', 'Released', 'Fab Order'
            ];

            // Check if first row is headers
            let startIdx = 0;
            const firstRow = lines[0].split(delimiter);
            if (firstRow.length === expectedColumns.length) {
                // Check if it looks like headers
                const firstRowLower = firstRow.map(cell => cell.toLowerCase().trim());
                const hasHeaderKeywords = expectedColumns.some((col, idx) =>
                    col.toLowerCase().includes(firstRowLower[idx]) ||
                    firstRowLower[idx].includes(col.toLowerCase().split(' ')[0])
                );
                if (hasHeaderKeywords) {
                    startIdx = 1;
                }
            }

            // Parse data rows
            const parsedRows = [];
            for (let i = startIdx; i < lines.length; i++) {
                const cells = lines[i].split(delimiter);
                if (cells.length === 0 || cells.every(cell => !cell.trim())) continue;

                // Pad with empty strings if needed
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

            // Unlock the modal immediately so user can cancel/edit/retry
            setReleasing(false);

            // Refresh in the background only if something was actually created
            if (result.created_count > 0) {
                fetchAll();
            }

            // Only auto-close if everything succeeded with no collisions
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
        const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
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

    const handlePrint = () => {
        // First, sort all jobs by Job # first, then PM
        const sortedJobs = [...jobs].sort((a, b) => {
            // First sort by Job #
            const jobA = a['Job #'] || 0;
            const jobB = b['Job #'] || 0;
            if (jobA !== jobB) {
                return jobA - jobB;
            }
            // Then sort by PM (treat null/empty as empty string for sorting)
            const pmA = (a['PM'] || '').toString().toLowerCase();
            const pmB = (b['PM'] || '').toString().toLowerCase();
            return pmA.localeCompare(pmB);
        });

        // Group jobs by PM, maintaining the sorted order within each PM group
        const jobsByPM = {};
        sortedJobs.forEach(job => {
            const pm = job['PM'] || 'No PM';
            if (!jobsByPM[pm]) {
                jobsByPM[pm] = [];
            }
            jobsByPM[pm].push(job);
        });

        Object.keys(jobsByPM).forEach(pm => {
            jobsByPM[pm].sort((a, b) => {
                const jobA = a['Job #'] || 0;
                const jobB = b['Job #'] || 0;
                if (jobA !== jobB) return jobA - jobB;
                return compareSameJob(a, b);
            });
        });

        // Create printable HTML
        let printHTML = `
<!DOCTYPE html>
<html>
<head>
    <title>Job Log - Print</title>
    <style>
        * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }
        @media print {
            @page {
                /* 11x17 tabloid in landscape orientation */
                size: 11in 17in landscape;
                margin: 0.5in;
            }
            /* Force each PM to start on a fresh front (right-hand) sheet so duplex
               printing never lands the next PM on the back of the previous one. */
            .pm-group {
                break-before: right;
                page-break-before: right;
            }
            .pm-group:first-child {
                break-before: auto;
                page-break-before: auto;
            }
        }
        body {
            font-family: Arial, sans-serif;
            font-size: 10px;
            margin: 0;
            padding: 20px;
        }
        h1 {
            font-size: 18px;
            margin-bottom: 10px;
            color: #333;
        }
        .pm-header {
            font-size: 14px;
            font-weight: bold;
            margin: 20px 0 10px 0;
            padding: 8px;
            background-color: #f0f0f0;
            border-bottom: 2px solid #333;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            table-layout: fixed;
        }
        .hard-date {
            background-color: #EF4444;
            color: white;
            font-weight: bold;
        }
        th {
            background-color: #e0e0e0;
            border: 1px solid #999;
            padding: 6px 4px;
            text-align: center;
            font-weight: bold;
            font-size: 9px;
            white-space: nowrap;
        }
        td {
            border: 1px solid #ccc;
            padding: 4px;
            text-align: center;
            font-size: 9px;
            overflow: hidden;
            text-overflow: ellipsis;
            word-wrap: break-word;
        }
        tr:nth-child(even) {
            background-color: #dbeafe;
        }
        tr.grayed-row, tr.grayed-row:nth-child(even) {
            background-color: #d1d5db;
        }
        .no-data {
            text-align: center;
            padding: 20px;
            color: #666;
        }
    </style>
</head>
<body>
    <h1>Job Log - Printed ${new Date().toLocaleString()}</h1>
`;

        // Generate table for each PM group.
        // PM blocks are ordered alphabetically by PM, with each block internally sorted by Job #.
        Object.keys(jobsByPM).sort((pmA, pmB) => {
            return pmA.toLowerCase().localeCompare(pmB.toLowerCase());
        }).forEach((pm) => {
            const pmJobs = jobsByPM[pm];

            // Build colgroup with normalized widths for uniform columns across pages
            const defaultWeight = 5;
            const totalWeight = columnHeaders.reduce((sum, col) => sum + (COLUMN_WIDTH_PERCENT[col] ?? defaultWeight), 0);
            const colgroup = '<colgroup>' + columnHeaders.map(col => {
                const pct = ((COLUMN_WIDTH_PERCENT[col] ?? defaultWeight) / totalWeight * 100).toFixed(2);
                return `<col style="width:${pct}%">`;
            }).join('') + '</colgroup>';

            printHTML += `
    <div class="pm-group">
        <div class="pm-header">PM: ${pm}</div>
        <table>
            ${colgroup}
            <thead>
                <tr>
                    ${columnHeaders.map(col => {
                const displayHeader = col === 'Release #' ? 'rel. #' : col === 'Job Comp' ? 'Install Prog' : col;
                return `<th>${displayHeader}</th>`;
            }).join('')}
                </tr>
            </thead>
            <tbody>
`;

            pmJobs.forEach(job => {
                const isInstallComplete = (job['Job Comp'] || '').toString().trim().toUpperCase() === 'X';
                const isComplete = isCompleteStage(job['Stage']);
                const isGrayed = isInstallComplete || isComplete;
                printHTML += `<tr${isGrayed ? ' class="grayed-row"' : ''}>`;
                columnHeaders.forEach(column => {
                    // Render Urgency column as colored banana SVGs
                    if (column === 'Urgency') {
                        const stage = job['Stage'] || 'Released';
                        const bananaColor = job['Banana Color'] || null;
                        const group = stageToGroup?.[stage] || 'FABRICATION';

                        let count = 1, defaultColor = 'gray';
                        if (group === 'FABRICATION') {
                            const colorMap = { 'Cut start': 'green', 'Material Ordered': 'green', 'Fit Up Complete.': 'yellow', 'Released': 'gray', 'Hold': 'red' };
                            defaultColor = colorMap[stage] || 'gray';
                            count = 1;
                        } else if (group === 'READY_TO_SHIP') {
                            const colorMap = { 'Welded QC': 'green', 'Paint complete': 'yellow', 'Store at MHMW for shipping': 'yellow', 'Shipping planning': 'yellow' };
                            defaultColor = colorMap[stage] || 'yellow';
                            count = 2;
                        } else if (group === 'COMPLETE') {
                            const colorMap = { 'Complete': 'gray', 'Shipping completed': 'green' };
                            defaultColor = colorMap[stage] || 'gray';
                            count = 3;
                        }

                        const isHold = stage === 'Hold';
                        const effectiveColor = isHold ? 'red' : (bananaColor === 'red' ? 'red' : defaultColor);

                        const fillMap = { red: '#EF4444', yellow: '#FFE135', green: '#22C55E', gray: '#9CA3AF' };
                        const fill = fillMap[effectiveColor] || fillMap.yellow;
                        const stroke = effectiveColor === 'gray' ? '#6B7280' : '#000000';

                        const bananaSvg = `<svg width="16" height="16" viewBox="0 0 950 927.611" xmlns="http://www.w3.org/2000/svg" style="display:inline-block;vertical-align:middle;"><g><g fill="${fill}" stroke="${stroke}" stroke-width="22"><path d="M158.56,618.97l2.4-0.7c97-26.199,181.6-59.8,251.2-99.8c94.5-54.3,159.4-119.5,193-193.799l16-35.4l-28.699,26.2c-57,52.1-134.801,91-231.4,115.8c-81.9,21-176,31.7-279.8,31.7c-5.4,0-17.4-0.1-24.6-0.2l-16.9-0.8c-13.3-0.6-25.4,7.6-29.8,20.2l-6.6,19.1c-3.9,11.301-0.7,23.9,8.2,32c7.4,6.7,14.9,13.2,14.9,13.2s56,48.5,129.6,71.7L158.56,618.97z"/><path d="M811.86,163.17c-29.1-13.4-56.899-15.4-70.899-15.4c-1.801,0-3.5,0-4.9,0.1c-3.2-11.2-19.4-78.1-30.7-124.9c-5.2-21.5-31.1-30.2-48.2-16.1l-53.6,44.2c-14,11.5-16.9,31.7-6.7,46.7c22.4,32.9,59.5,91.7,77.7,144.8c17.2,50.3,18.7,102.9,10.5,154.6c-13.4,83.7-57.6,168.2-131.4,251.2c-40.199,45.2-84.699,86.399-132.199,123.7c-23.801,18.699-48.4,36.399-73.7,53c-2.601,1.699-32.7,19.399-53.601,30.199c-11.699,6-18.1,19-15.8,31.9l2.5,14c2.4,13.4,13.5,23.5,27,24.6c34.3,2.9,105.101,4.801,199.7-13.899c51.8-10.2,101.8-34.5,148.2-62.101c78.1-46.6,182.8-131.399,238.1-271c24.7-62.3,35.2-126.699,31.2-191.599c-3.9-63.8-20.7-112.4-34.1-142C873.66,206.771,847.06,179.271,811.86,163.17z"/><path d="M109.46,744.97c13.1,8.101,34.4,19.8,60.3,28.4c44.5,14.8,91.8,21.2,138.5,22.7l2.6,0.1l2.101-1.4c34.5-23.1,67.3-47.3,97.6-71.899c37.7-30.7,71.5-62.2,100.5-93.601c26.3-28.5,50.6-58.899,71.4-91.6c18.199-28.6,33.699-59.1,44.8-91.2c5.2-15,9.5-30.399,12.399-46.1c3-15.9,4.4-32.1,6.5-48.2c0.4-3.2,0.801-6.3,1.2-9.5l-19.899,33.9c-41.7,71.199-110.5,133.699-204.601,186c-61.2,34.1-126.8,60.1-193.6,81.199c-36.4,11.5-71.6,21.601-108.6,27.301c-14.6,2.199-25.3,14.8-25.3,29.6c0,6.4,0,13.1,0,18.9C95.36,729.87,100.66,739.47,109.46,744.97z"/></g></g></svg>`;

                        const bgMap = { red: '#FEE2E2', yellow: '#FEF9C3', green: '#D1FAE5', gray: '#F3F4F6' };
                        const borderMap = { red: '#FCA5A5', yellow: '#FDE68A', green: '#6EE7B7', gray: '#D1D5DB' };
                        const bg = bgMap[effectiveColor] || bgMap.gray;
                        const border = borderMap[effectiveColor] || borderMap.gray;

                        printHTML += `<td style="text-align:center;"><span style="display:inline-flex;align-items:center;gap:2px;padding:2px 4px;border-radius:4px;background:${bg};border:1px solid ${border};">${Array(count).fill(bananaSvg).join('')}</span></td>`;
                        return;
                    }

                    let value = job[column];

                    // Format date columns
                    if (column === 'Released' || column === 'Start install' || column === 'Comp. ETA') {
                        value = formatDate(value);
                    } else {
                        value = formatCellValue(value, column);
                    }

                    // Escape HTML
                    const displayValue = String(value || '—').replace(/</g, '&lt;').replace(/>/g, '&gt;');

                    // Apply red styling for hard dates on Start install
                    const isHardDate = column === 'Start install' && job['start_install_formulaTF'] === false && job['Start install'];
                    printHTML += `<td${isHardDate ? ' class="hard-date"' : ''}>${displayValue}</td>`;
                });
                printHTML += '</tr>';
            });

            printHTML += `
            </tbody>
        </table>
    </div>
`;
        });

        printHTML += `
</body>
</html>
`;

        // Open print window
        const printWindow = window.open('', '_blank');
        printWindow.document.write(printHTML);
        printWindow.document.close();

        // Wait for content to load, then trigger print
        printWindow.onload = () => {
            setTimeout(() => {
                printWindow.print();
            }, 250);
        };
    };

    return (
        <>
            <div className="w-full h-[calc(100vh-3.5rem)] bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 py-2 px-2 flex flex-col" style={{ width: '100%', minWidth: '100%' }}>
                <div className="max-w-full mx-auto w-full h-full flex flex-col" style={{ width: '100%' }}>
                    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col h-full">

                        <div className="p-2 flex flex-col flex-1 min-h-0 space-y-1.5">
                            <div className="bg-gray-100 dark:bg-slate-700 rounded-lg p-1.5 border border-gray-200 dark:border-slate-600 flex-shrink-0 space-y-1.5">

                                {/* Minimized project pills — show selected projects when collapsed */}
                                {isFilterMinimized && selectedProjectNames.length > 0 && (
                                    <div className="flex items-center gap-1 flex-wrap text-xs">
                                        <span className="font-semibold text-gray-500 dark:text-slate-400">Projects:</span>
                                        {selectedProjectNames.map(name => (
                                            <span key={name} className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded-full font-medium">
                                                {name}
                                            </span>
                                        ))}
                                    </div>
                                )}

                                {/* Row 1: Project name buttons — only visible when expanded */}
                                {!isFilterMinimized && (
                                    <div className="grid gap-1" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))' }}>
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

                                {/* Row 2: Actions (left) + Stage filters (center-right) + Chevron (far right) — always visible */}
                                <div className="flex items-center gap-1.5">
                                    {/* Action buttons inline */}
                                    <div className="flex items-center gap-1.5">
                                        <button
                                            onClick={handlePrint}
                                            disabled={!hasData || loading}
                                            className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500 disabled:opacity-40 disabled:cursor-not-allowed"
                                        >
                                            🖨️ Print
                                        </button>
                                        <button
                                            onClick={() => navigate('/pm-board')}
                                            className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500"
                                        >
                                            📋 PM Board
                                        </button>
                                        <button
                                            onClick={() => navigate('/archive')}
                                            className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500"
                                        >
                                            🗄️ Archive
                                        </button>
                                        {isAdmin && (
                                            <button
                                                onClick={handleExportCSV}
                                                disabled={!hasData || loading}
                                                className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500 disabled:opacity-40 disabled:cursor-not-allowed"
                                                title="Admin only — download the currently filtered job log rows as a CSV file. Respects the active project, stage subset, search, and Review-mode filters/sort."
                                            >
                                                ⬇️ Export CSV
                                            </button>
                                        )}
                                        {isAdmin && (
                                            <button
                                                onClick={async () => {
                                                    try {
                                                        const data = await jobsApi.getArchivePreview();
                                                        setArchivePreview(data);
                                                        setShowArchiveModal(true);
                                                    } catch (err) {
                                                        alert(`Failed to load archive preview: ${err.message}`);
                                                    }
                                                }}
                                                className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-amber-50 dark:bg-amber-900/30 border border-amber-400 dark:border-amber-600 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/50"
                                            >
                                                Send to Archive
                                            </button>
                                        )}
                                        {isAdmin && (
                                            <button
                                                onClick={async () => {
                                                    try {
                                                        const data = await jobsApi.renumberFabricationFabOrders({ dryRun: true });
                                                        setRenumberPreview(data);
                                                        setShowRenumberModal(true);
                                                    } catch (err) {
                                                        alert(`Failed to load renumber preview: ${err.message}`);
                                                    }
                                                }}
                                                className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-amber-50 dark:bg-amber-900/30 border border-amber-400 dark:border-amber-600 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/50"
                                                title="Admin only — compress FABRICATION group fab_order values to a contiguous block starting at 3, preserving relative order. Welded QC and later stages are untouched."
                                            >
                                                🔢 Renumber Fab Order
                                            </button>
                                        )}
                                        <button
                                            onClick={handleReleaseClick}
                                            className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500"
                                        >
                                            📋 Release
                                        </button>
                                    </div>

                                    {/* Stage filter buttons */}
                                    <div className="flex items-center gap-1.5 flex-wrap flex-1 justify-center">
                                        <button
                                            onClick={() => {
                                                setReviewMode(false);
                                                setSelectedSubset(selectedSubset === 'job_order' ? null : 'job_order');
                                            }}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${selectedSubset === 'job_order'
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                                                }`}
                                            title="Show all active releases sorted by the unified Fab Order sequence. Useful for seeing the full production queue in order."
                                        >
                                            Job Order
                                        </button>
                                        <button
                                            onClick={() => {
                                                setReviewMode(false);
                                                setSelectedSubset(selectedSubset === 'ready_to_ship' ? null : 'ready_to_ship');
                                            }}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${selectedSubset === 'ready_to_ship'
                                                ? 'bg-emerald-600 text-white'
                                                : 'bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                                                }`}
                                            title="Show only releases in Shipping planning, Store at MHMW for shipping, or Paint complete — i.e., work that's finished production and ready to leave."
                                        >
                                            Ready to Ship
                                        </button>
                                        <button
                                            onClick={() => {
                                                setReviewMode(false);
                                                setSelectedSubset(selectedSubset === 'paint' ? null : 'paint');
                                            }}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${selectedSubset === 'paint'
                                                ? 'bg-emerald-600 text-white'
                                                : 'bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                                                }`}
                                            title="Show only releases in Welded QC or Paint Start stages, sorted by Fab Order. Use to focus on jobs currently in paint."
                                        >
                                            Paint
                                        </button>
                                        <button
                                            onClick={() => {
                                                setReviewMode(false);
                                                setSelectedSubset(selectedSubset === 'paint_fab' ? null : 'paint_fab');
                                            }}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${selectedSubset === 'paint_fab'
                                                ? 'bg-emerald-600 text-white'
                                                : 'bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                                                }`}
                                            title="Combined view of Paint stages (Welded QC, Paint Start, Paint complete) followed by all Fabrication-group stages, sorted by Fab Order with Start Install date as tiebreaker."
                                        >
                                            Paint+Fab
                                        </button>
                                        <button
                                            onClick={() => {
                                                setReviewMode(false);
                                                setSelectedSubset(selectedSubset === 'fab' ? null : 'fab');
                                            }}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${selectedSubset === 'fab'
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                                                }`}
                                            title="Show only releases in the Fabrication stage group, sorted by Fab Order. Use to focus on shop floor work."
                                        >
                                            Fab
                                        </button>
                                        <button
                                            onClick={() => {
                                                const next = !reviewMode;
                                                if (next) setSelectedSubset(null);
                                                setReviewMode(next);
                                            }}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${reviewMode
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                                                }`}
                                            title="Group releases by PM (alphabetical), then by Project # ascending, with the most-complete stage first within each project. Intended for PM review meetings."
                                        >
                                            Review
                                        </button>
                                    </div>

                                    {/* Chevron toggle button */}
                                    <button
                                        onClick={() => setIsFilterMinimized(!isFilterMinimized)}
                                        className="p-1.5 rounded-lg hover:bg-gray-300 dark:hover:bg-slate-600 transition-colors flex-shrink-0"
                                        title={isFilterMinimized ? "Expand projects" : "Collapse projects"}
                                    >
                                        <span className="text-xl leading-none text-gray-600 dark:text-slate-300">{isFilterMinimized ? '▾' : '▴'}</span>
                                    </button>
                                </div>

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
                                                className="w-64 px-2 py-0.5 text-xs border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-600 text-gray-900 dark:text-slate-100"
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
                                    <div className="flex items-center gap-3 text-xs font-semibold text-gray-700 dark:text-slate-200">
                                        <span>
                                            Total: <span className="text-gray-900 dark:text-slate-100 font-bold">{displayJobs.length}</span> records
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
                            </div>



                            {loading && (
                                <div className="text-center py-12">
                                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                    <p className="text-gray-600 font-medium">Loading Jobs data...</p>
                                </div>
                            )}

                            {fetchError && !loading && (
                                <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm">
                                    <div className="flex items-start">
                                        <span className="text-xl mr-3">⚠️</span>
                                        <div>
                                            <p className="font-semibold">Unable to load Jobs data</p>
                                            <p className="text-sm mt-1">{fetchError}</p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {!loading && !fetchError && (
                                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
                                    <div ref={tableScrollRef} className="job-log-table-scroll-hide-scrollbar overflow-auto flex-1">
                                        <table className="w-full" style={{ borderCollapse: 'collapse', tableLayout: 'fixed', width: '100%' }}>
                                            <thead className="sticky top-0 z-10">
                                                <tr>
                                                    {columnHeaders.map((column) => {
                                                        const isReleaseNumber = column === 'Release #';
                                                        // Display "rel. #" for Release # column header
                                                        const displayHeader = column === 'Release #' ? 'rel. #' : column === 'Job Comp' ? 'Install Prog' : column;
                                                        const colWidthPct = columnWidthPercents[column];
                                                        const isFilterable = FILTERABLE_COLUMNS.has(column);
                                                        const colInfo = isFilterable ? uniqueValuesByColumn[column] : null;
                                                        const colSelected = columnFilters[column] ?? [];
                                                        return (
                                                            <th
                                                                key={column}
                                                                className={`${isReleaseNumber ? 'px-1' : 'px-2'} ${isOldMan ? 'py-2 text-xs' : 'py-0.5 text-[10px]'} text-center font-bold text-gray-700 dark:text-slate-200 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-b-2 border-gray-300 dark:border-slate-600`}
                                                                style={colWidthPct != null ? { width: `${colWidthPct}%` } : undefined}
                                                            >
                                                                {isFilterable ? (
                                                                    <ColumnHeaderFilter
                                                                        column={column}
                                                                        values={colInfo?.values ?? []}
                                                                        hasBlanks={colInfo?.hasBlanks ?? false}
                                                                        selected={new Set(colSelected)}
                                                                        onChange={(next) => setColumnFilter(column, [...next])}
                                                                        sort={columnSort}
                                                                        onSort={(dir) => setColumnSort(column, dir)}
                                                                        isActive={colSelected.length > 0}
                                                                    >
                                                                        {displayHeader}
                                                                    </ColumnHeaderFilter>
                                                                ) : (
                                                                    displayHeader
                                                                )}
                                                            </th>
                                                        );
                                                    })}
                                                    {isAdmin && (
                                                        <th className="px-2 py-0.5 text-center text-xl font-bold text-gray-700 dark:text-slate-200 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-b-2 border-gray-300 dark:border-slate-600 w-12">
                                                            ⚙
                                                        </th>
                                                    )}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {!hasData ? (
                                                    hasJobsData && search.trim() !== '' && secondarySearchResults.length > 0 ? (
                                                        <>
                                                            <tr>
                                                                <td
                                                                    colSpan={tableColumnCount + (isAdmin ? 1 : 0)}
                                                                    className="px-6 py-6 text-center text-amber-800 dark:text-amber-200 font-medium bg-amber-50 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800"
                                                                >
                                                                    <span className="mr-2">⚠️</span>
                                                                    {`'${search.trim()}' not found under current filters. Showing results from unfiltered search:`}
                                                                </td>
                                                            </tr>
                                                            {secondarySearchResults.map((row, index) => (
                                                                <JobsTableRow
                                                                    key={row.id}
                                                                    row={row}
                                                                    columns={columnHeaders}
                                                                    isJumpToHighlight={jumpToTarget && String(row['Job #']) === jumpToTarget.job && String(row['Release #']) === jumpToTarget.release}
                                                                    formatCellValue={(value, columnName) => formatCellValue(value, columnName)}
                                                                    formatDate={formatDate}
                                                                    rowIndex={index}
                                                                    onDragStart={handleDragStart}
                                                                    onDragOver={handleDragOver}
                                                                    onDragLeave={handleDragLeave}
                                                                    onDrop={handleDrop}
                                                                    isDragging={draggedIndex}
                                                                    dragOverIndex={dragOverIndex}
                                                                    onUpdate={() => refetch(true)}
                                                                    onCascadeRecalculating={handleCascadeRecalculating}
                                                                    stageToGroup={stageToGroup}
                                                                    stageGroupColors={stageGroupColors}
                                                                    stageGroupDupColors={stageGroupDupColors}
                                                                    isAdmin={isAdmin}
                                                                    onDelete={handleDeleteJob}
                                                                    tableScrollRef={tableScrollRef}
                                                                    duplicateFabOrders={duplicateFabOrders}
                                                                />
                                                            ))}
                                                        </>
                                                    ) : (
                                                        <tr>
                                                            <td
                                                                colSpan={tableColumnCount + (isAdmin ? 1 : 0)}
                                                                className="px-6 py-12 text-center text-gray-500 dark:text-slate-400 font-medium bg-white dark:bg-slate-800 rounded-md"
                                                            >
                                                                {hasJobsData
                                                                    ? 'No records match the selected filters.'
                                                                    : 'No records found.'
                                                                }
                                                            </td>
                                                        </tr>
                                                    )
                                                ) : (
                                                    reviewDisplayJobs.map((row, index) => (
                                                        <JobsTableRow
                                                            key={row.id}
                                                            row={row}
                                                            columns={columnHeaders}
                                                            isJumpToHighlight={jumpToTarget && String(row['Job #']) === jumpToTarget.job && String(row['Release #']) === jumpToTarget.release}
                                                            formatCellValue={(value, columnName) => formatCellValue(value, columnName)}
                                                            formatDate={formatDate}
                                                            rowIndex={index}
                                                            onDragStart={handleDragStart}
                                                            onDragOver={handleDragOver}
                                                            onDragLeave={handleDragLeave}
                                                            onDrop={handleDrop}
                                                            isDragging={draggedIndex}
                                                            dragOverIndex={dragOverIndex}
                                                            onUpdate={() => refetch(true)}
                                                            onCascadeRecalculating={handleCascadeRecalculating}
                                                            stageToGroup={stageToGroup}
                                                            stageGroupColors={stageGroupColors}
                                                            stageGroupDupColors={stageGroupDupColors}
                                                            isAdmin={isAdmin}
                                                            onDelete={handleDeleteJob}
                                                            tableScrollRef={tableScrollRef}
                                                            duplicateFabOrders={duplicateFabOrders}
                                                        />
                                                    ))
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}
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

export default JobLog;

