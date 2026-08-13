/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Renders a single job-log table row with inline stage editing, urgency indicators, action menus, and detail/date modals.
 * exports:
 *   JobsTableRow: Feature-rich table row for the Job Log with inline editing and admin actions
 * imports_from: [react, ../services/jobsApi, ../constants/jumpToHighlight, ./ReleaseHubModal, ./StartInstallDateModal, ./StageIconRow]
 * imported_by: [frontend/src/pages/JobLog.jsx, frontend/src/pages/Archive.jsx]
 * invariants:
 *   - Stage dropdown options must stay in sync with constants/stages.js definitions
 *   - Delete / unarchive stay admin-only; row-field edit (job→released) is admin or drafter (DP)
 *   - Duplicate fab order detection relies on the duplicateFabOrders set passed from parent
 * updated_by_agent: 2026-08-06T00:00:00Z
 */
import React, { useState, useEffect, useRef, useMemo } from 'react';
import { jobsApi } from '../services/jobsApi';
import { setAsapAndAssign } from '../utils/asap';
import { localTodayStr, toYmd, formatFabOrder } from '../utils/formatters';
import { JUMP_TO_HIGHLIGHT_CLASS } from '../constants/jumpToHighlight';
import { ReleaseHubModal } from './ReleaseHubModal';
import { MaterialOrderBadge } from './MaterialOrderBadge';
import { StartInstallDateModal } from './StartInstallDateModal';
import { StageIconRow } from './StageIconRow';
import { ASAP_PROPAGATED_ROW_CLASS } from './AsapPropagationTag';
import { PdfMarkupModal } from './PdfMarkupModal';
import { PdfVersionHistoryModal } from './PdfVersionHistoryModal';
import { useTheme } from '../context/ThemeContext';
import { useReleases } from '../context/ReleasesContext';

// Master switch for the stage photo gate. Held OFF for now — the gate UI/infra
// stays in place so flipping this back to true re-enables it. Keep in sync with
// the backend flag STAGE_PHOTO_GATE_ENABLED in stage/command.py.
const STAGE_PHOTO_GATE_ENABLED = false;

// Stages that require a stage-tagged photo before a release may enter them.
// Selecting one opens the attachment modal in gate mode instead of changing
// the stage immediately. The backend enforces the same gate (422 photo_required).
const STAGE_PHOTO_GATES = ['Welded QC', 'Paint Complete'];

export function JobsTableRow({ row, columns, formatCellValue, formatDate, rowIndex, bandIndex = null, onDragStart, onDragOver, onDragLeave, onDrop, isDragging, dragOverIndex, onUpdate, onCascadeRecalculating = null, stageToGroup, stageGroupColors, stageGroupDupColors = null, isJumpToHighlight, isAdmin = false, isDrafter = false, onDelete = null, onUnarchive = null, tableScrollRef = null, duplicateFabOrders = null, compact = false, showActions = true }) {
    const { refreshMaterialSummary } = useReleases();
    const [isModalOpen, setIsModalOpen] = useState(false);
    // Which tab the release hub opens on. The Description cell lands on Details;
    // nothing else in the row opens it directly today.
    const [hubTab, setHubTab] = useState('details');
    // When the modal is opened from the Mat. Ord. cell, jump straight to the
    // Materials Ordered section instead of the top of the modal.
    const [modalScrollToMaterials, setModalScrollToMaterials] = useState(false);
    const [isStartInstallModalOpen, setIsStartInstallModalOpen] = useState(false);
    const [pdfMarkupOpen, setPdfMarkupOpen] = useState(false);
    const [pdfMarkupVersionId, setPdfMarkupVersionId] = useState(null);
    const [pdfMarkupMode, setPdfMarkupMode] = useState('edit');
    const [pdfHistoryOpen, setPdfHistoryOpen] = useState(false);
    // When set, the attachment modal is opened in stage-gate mode for this stage:
    // a photo tagged with it must be uploaded before the stage change applies.
    const [gateStage, setGateStage] = useState(null);
    const [showActionMenu, setShowActionMenu] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [fieldValues, setFieldValues] = useState({});
    const [saving, setSaving] = useState(false);

    // has_drawing used to decide whether the Release # cell opened the drawing
    // hub or linked to Procore. Both live on the release hub now, so the row no
    // longer branches on it.

    // Uploading, viewing, and marking up drawings/photos is open to every
    // logged-in user (deleting a drawing version stays admin-only on the
    // backend). The attachment hub therefore opens in edit mode for everyone.
    const canMarkup = true;

    // Single entry point for the release hub. The Description cell is the row's
    // only hyperlink — Job and Release # are plain text — so anything else that
    // needs the hub (the Mat. Ord. glyph) routes through here with a tab.
    const openHub = (tab = 'details', { scrollToMaterials = false } = {}) => {
        setHubTab(tab);
        setModalScrollToMaterials(scrollToMaterials);
        setIsModalOpen(true);
    };

    // Check if row should be grayed (Complete status or both Job Comp and Invoiced are X).
    // Tolerates whitespace + case drift on the stage value.
    const isComplete = (row['Stage'] || '').toString().trim().toLowerCase() === 'complete';

    // Row is draggable (disabled for now)
    const isDraggable = false;

    // Stage options with simplified names for display (in progression order)
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Material Ordered', label: 'Mat. Order' },
        { value: 'Cut Start', label: 'Cut Start' },
        { value: 'Cut Complete', label: 'Cut comp' },
        { value: 'Fitup Start', label: 'Fitup start' },
        { value: 'Fitup Complete', label: 'Fitup comp' },
        { value: 'Weld Start', label: 'Weld start' },
        { value: 'Weld Complete', label: 'Weld comp' },
        { value: 'Welded QC', label: 'Welded QC' },
        { value: 'Paint Start', label: 'Paint Start' },
        { value: 'Paint Complete', label: 'Paint comp' },
        { value: 'Hold', label: 'Hold' },
        { value: 'Store at MHMW', label: 'Store' },
        { value: 'Ship Planning', label: 'Ship plan' },
        { value: 'Ship Complete', label: 'Ship comp' },
        { value: 'Install Start', label: 'Install start' },
        { value: 'Install Complete', label: 'Install comp' },
        { value: 'Complete', label: 'Complete' }
    ];

    // Color mapping for each stage
    const stageColors = {
        'Released': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Cut Start': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Cut Complete': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Fitup Start': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Fitup Complete': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        // Welded QC + Paint Start sit in READY_TO_SHIP on the print PDF (green),
        // not amber — keep the fallback map aligned when stageGroupColors is absent.
        'Welded QC': {
            light: 'rgb(209 250 229)', // emerald-100
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Paint Start': {
            light: 'rgb(209 250 229)', // emerald-100
            base: 'rgb(16 185 129)',
            dark: 'rgb(5 150 105)',
            text: 'rgb(6 95 70)',
            border: 'rgb(110 231 183)',
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Paint Complete': {
            light: 'rgb(209 250 229)', // emerald-100 (green)
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Store at MHMW': {
            light: 'rgb(209 250 229)', // emerald-100 (green)
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Ship Planning': {
            light: 'rgb(209 250 229)', // emerald-100 (green)
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Ship Complete': {
            light: 'rgb(237 233 254)', // violet-100 (gentle purple)
            base: 'rgb(139 92 246)', // violet-500
            dark: 'rgb(124 58 237)', // violet-600
            text: 'rgb(91 33 182)', // violet-800
            border: 'rgb(196 181 253)', // violet-300
            className: 'bg-violet-100 text-violet-800 border-violet-300'
        },
        'Install Start': {
            light: 'rgb(237 233 254)', // violet-100 (gentle purple)
            base: 'rgb(139 92 246)', // violet-500
            dark: 'rgb(124 58 237)', // violet-600
            text: 'rgb(91 33 182)', // violet-800
            border: 'rgb(196 181 253)', // violet-300
            className: 'bg-violet-100 text-violet-800 border-violet-300'
        },
        'Install Complete': {
            light: 'rgb(237 233 254)', // violet-100 (gentle purple)
            base: 'rgb(139 92 246)', // violet-500
            dark: 'rgb(124 58 237)', // violet-600
            text: 'rgb(91 33 182)', // violet-800
            border: 'rgb(196 181 253)', // violet-300
            className: 'bg-violet-100 text-violet-800 border-violet-300'
        },
        'Complete': {
            light: 'rgb(237 233 254)', // violet-100 (gentle purple)
            base: 'rgb(139 92 246)', // violet-500
            dark: 'rgb(124 58 237)', // violet-600
            text: 'rgb(91 33 182)', // violet-800
            border: 'rgb(196 181 253)', // violet-300
            className: 'bg-violet-100 text-violet-800 border-violet-300'
        },
        'Hold': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Weld Start': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Weld Complete': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Material Ordered': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        }
    };

    // Local state for stage
    const [localStage, setLocalStage] = useState(row['Stage'] || 'Released');
    const [updatingStage, setUpdatingStage] = useState(false);

    // Local state for fab order
    const [localFabOrder, setLocalFabOrder] = useState(row['Fab Order'] ?? '');
    const [updatingFabOrder, setUpdatingFabOrder] = useState(false);
    // formatFabOrder keeps the 80.555 placeholder at three decimals in the input.
    const [fabOrderInputValue, setFabOrderInputValue] = useState(
        () => formatFabOrder(row['Fab Order'] ?? ''),
    );

    // Local state for notes
    const [localNotes, setLocalNotes] = useState(row['Notes'] ?? '');
    const [updatingNotes, setUpdatingNotes] = useState(false);
    const [notesInputValue, setNotesInputValue] = useState(row['Notes'] ?? '');

    // Local state for start install
    const [localStartInstall, setLocalStartInstall] = useState(row['Start install'] ?? null);
    const [updatingStartInstall, setUpdatingStartInstall] = useState(false);
    // Local state for ship date (independent hard date; no Trello/scheduling side effects)
    const [localShipDate, setLocalShipDate] = useState(row['Ship Date'] ?? null);

    const [showStageDropdown, setShowStageDropdown] = useState(false);
    const [dropdownDirection, setDropdownDirection] = useState('down');
    const stageListRef = useRef(null);       // ref on the scrollable container div
    const selectedStageRef = useRef(null);   // ref on the currently-selected option button
    const stageTriggerRef = useRef(null);    // ref on the dropdown trigger button

    // Local state for Job Comp and Invoiced (editable text)
    const [localJobComp, setLocalJobComp] = useState(row['Job Comp'] ?? '');
    const [localInvoiced, setLocalInvoiced] = useState(row['Invoiced'] ?? '');
    const [jobCompInputValue, setJobCompInputValue] = useState(row['Job Comp'] ?? '');
    const [invoicedInputValue, setInvoicedInputValue] = useState(row['Invoiced'] ?? '');
    const [updatingJobComp, setUpdatingJobComp] = useState(false);
    const [updatingInvoiced, setUpdatingInvoiced] = useState(false);

    // Editable columns for the gear/⋯ edit modal (job → released).
    // Admins and drafters (DP); not inline — accidental delete risk per Bill.
    const canEditRowFields = isAdmin || isDrafter;
    const EDITABLE_COLUMNS = [
        { label: 'Job #', field: 'job', type: 'number' },
        { label: 'Release #', field: 'release', type: 'text' },
        { label: 'Job', field: 'job_name', type: 'text' },
        { label: 'Description', field: 'description', type: 'text' },
        { label: 'Fab Hrs', field: 'fab_hrs', type: 'number' },
        { label: 'Install HRS', field: 'install_hrs', type: 'number' },
        { label: 'Paint color', field: 'paint_color', type: 'text' },
        { label: 'PM', field: 'pm', type: 'text' },
        { label: 'BY', field: 'by', type: 'text' },
        { label: 'Released', field: 'released', type: 'date' },
    ];

    // Handlers for the full-row edit modal
    const handleOpenRowEdit = () => {
        const initialValues = {};
        EDITABLE_COLUMNS.forEach(col => {
            initialValues[col.field] = row[col.label] || '';
        });
        setFieldValues(initialValues);
        setShowActionMenu(false);
        setShowEditModal(true);
    };

    const handleSaveEdit = async () => {
        const changed = {};
        EDITABLE_COLUMNS.forEach(col => {
            const original = row[col.label] || '';
            const next = fieldValues[col.field] ?? '';
            if (next !== original) {
                changed[col.field] = next;
            }
        });

        if (Object.keys(changed).length === 0) {
            setShowEditModal(false);
            return;
        }

        setSaving(true);
        try {
            await jobsApi.updateJobFields(row['Job #'], row['Release #'], changed);
            onUpdate && onUpdate();
            setShowEditModal(false);
        } catch (error) {
            console.error('Failed to update job:', error);
            alert('Failed to update job: ' + error.message);
        } finally {
            setSaving(false);
        }
    };

    const handleDeleteRow = async () => {
        if (!window.confirm(`Delete job ${row['Job #']}-${row['Release #']}?`)) {
            return;
        }

        setShowActionMenu(false);

        try {
            onDelete && await onDelete(row);
        } catch (error) {
            console.error('Failed to delete job:', error);
            alert('Failed to delete job: ' + error.message);
        }
    };

    const handleUnarchiveRow = async () => {
        if (!window.confirm(`Unarchive job ${row['Job #']}-${row['Release #']}? This will move it back to the active job log.`)) {
            return;
        }

        setShowActionMenu(false);

        try {
            onUnarchive && await onUnarchive(row);
        } catch (error) {
            console.error('Failed to unarchive job:', error);
            alert('Failed to unarchive job: ' + error.message);
        }
    };

    // Sync local state when row data changes (e.g., on refresh)
    useEffect(() => {
        setLocalStage(row['Stage'] || 'Released');
        setLocalFabOrder(row['Fab Order'] ?? '');
        setFabOrderInputValue(formatFabOrder(row['Fab Order'] ?? ''));
        setLocalNotes(row['Notes'] ?? '');
        setNotesInputValue(row['Notes'] ?? '');
        setLocalStartInstall(row['Start install'] ?? null);
        setLocalShipDate(row['Ship Date'] ?? null);
        setLocalJobComp(row['Job Comp'] ?? '');
        setLocalInvoiced(row['Invoiced'] ?? '');
        setJobCompInputValue(row['Job Comp'] ?? '');
        setInvoicedInputValue(row['Invoiced'] ?? '');
    }, [row['Stage'], row['Fab Order'], row['Notes'], row['Start install'], row['Ship Date'], row['Job Comp'], row['Invoiced']]);

    // Rotate stage options so current stage is at top (wheel behavior)
    const rotatedStageOptions = useMemo(() => {
        const baseOptions = stageToGroup
            ? [...stageOptions].sort((a, b) => {
                const groupOrder = { FABRICATION: 0, READY_TO_SHIP: 1, COMPLETE: 2 };
                const ga = stageToGroup[a.value] ?? 'FABRICATION';
                const gb = stageToGroup[b.value] ?? 'FABRICATION';
                return (groupOrder[ga] ?? 0) - (groupOrder[gb] ?? 0);
              })
            : stageOptions;

        const idx = baseOptions.findIndex(o => o.value === localStage);
        if (idx <= 0) return baseOptions;
        return [...baseOptions.slice(idx), ...baseOptions.slice(0, idx)];
    }, [localStage, stageToGroup]);

    // Determine dropdown direction (up/down) when opened
    useEffect(() => {
        if (!showStageDropdown || !stageTriggerRef.current) return;

        const scrollContainer = tableScrollRef?.current;
        if (!scrollContainer) { setDropdownDirection('down'); return; }

        const containerRect = scrollContainer.getBoundingClientRect();
        const buttonRect = stageTriggerRef.current.getBoundingClientRect();
        const dropdownMaxHeight = 256; // max-h-64 = 16rem = 256px

        const spaceBelow = containerRect.bottom - buttonRect.bottom;
        const spaceAbove = buttonRect.top - containerRect.top;

        if (spaceBelow < dropdownMaxHeight && spaceAbove > spaceBelow) {
            setDropdownDirection('up');
        } else {
            setDropdownDirection('down');
        }
    }, [showStageDropdown]);

    // Close dropdown when table scrolls
    useEffect(() => {
        if (!showStageDropdown) return;

        const scrollContainer = tableScrollRef?.current;
        if (!scrollContainer) return;

        const handleScroll = () => setShowStageDropdown(false);
        scrollContainer.addEventListener('scroll', handleScroll, { passive: true });

        return () => scrollContainer.removeEventListener('scroll', handleScroll);
    }, [showStageDropdown]);

    const { isOldMan } = useTheme();
    const jobCompIsX = (localJobComp || '').toString().trim().toUpperCase() === 'X';
    const invoicedIsX = (localInvoiced || '').toString().trim().toUpperCase() === 'X';
    const isGrayed = isComplete || jobCompIsX;
    // Row bands match jobLogPdf.js (print source of truth): white / blue-100
    // (#dbeafe) zebra, gray-400 (#9ca3af) for complete. `bandIndex` counts only
    // non-complete rows so a grey row doesn't break zebra adjacency. Falls back
    // to rowIndex when the parent hasn't supplied one.
    const bandParity = (bandIndex ?? rowIndex) % 2;
    const rowBgClass = isGrayed ? 'jl-band-done' : (bandParity === 0 ? 'jl-band-a' : 'jl-band-b');
    // Lattice borders come from .job-log-table in tokens.css (border-right /
    // border-bottom on td) — no per-cell shadow classes.
    const cellPy = isOldMan ? 'py-2' : 'py-0.5';
    const cellText = 'text-jl';
    // Numbers, dates and ids keep the handoff's `font-mono` marker. It is no
    // longer a second typeface — Calibri is the whole app now — but Calibri's
    // digits sit on one fixed advance, so these columns still stack.
    const cellMono = 'font-mono';
    // Editors read as plain text at rest and only show their box on hover/focus.
    // This is styling only — every input keeps the exact behavior it had, which
    // is why the border is revealed rather than removed.
    const quietInput = 'bg-transparent border border-transparent hover:border-hairline-strong focus:bg-input-bg focus:border-brand';

    // Handle stage change. Gated stages (Welded QC / Paint Complete) require a
    // tagged photo first: open the attachment modal in gate mode and defer the
    // actual change until the user confirms. All other stages apply immediately.
    const handleStageChange = (newStage) => {
        if (STAGE_PHOTO_GATE_ENABLED && STAGE_PHOTO_GATES.includes(newStage) && newStage !== localStage) {
            setGateStage(newStage);
            setPdfHistoryOpen(true);
            return;
        }
        applyStageChange(newStage);
    };

    // Perform the stage update (optimistic UI + API call + refetch).
    const applyStageChange = async (newStage) => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];

        const oldStage = localStage;
        const oldJobComp = localJobComp;
        const oldFabOrder = localFabOrder;
        setLocalStage(newStage); // Optimistic update
        // 'Install Complete' and 'Complete' form one "complete zone" for the
        // Install Prog marker: entering it sets job_comp='X', leaving it clears
        // the 'X' (mirrors the backend cascade in stage/command.py).
        const COMPLETE_ZONE = ['Install Complete', 'Complete'];
        if (COMPLETE_ZONE.includes(newStage)) {
            setLocalJobComp('X');
            setJobCompInputValue('X');
            setLocalFabOrder(null);
            setFabOrderInputValue('');
        }
        if (COMPLETE_ZONE.includes(oldStage) && !COMPLETE_ZONE.includes(newStage)) {
            if ((localJobComp || '').trim().toUpperCase() === 'X') {
                setLocalJobComp('');
                setJobCompInputValue('');
            }
        }
        setUpdatingStage(true);
        if (onCascadeRecalculating) onCascadeRecalculating(true);

        try {
            console.log(`[STAGE] Updating job ${jobNumber}-${releaseNumber} from ${oldStage} to ${newStage}`);

            await jobsApi.updateStage(jobNumber, releaseNumber, newStage);

            console.log(`[STAGE] Successfully updated job ${jobNumber}-${releaseNumber} to ${newStage}`);

            // Trigger refetch to show latest state
            if (onUpdate) {
                onUpdate();
            }
        } catch (error) {
            console.error(`[STAGE] Failed to update stage for job ${row['Job #']}-${row['Release #']}:`, error);
            // Revert on error
            setLocalStage(oldStage);
            setLocalJobComp(oldJobComp);
            setJobCompInputValue(oldJobComp ?? '');
            setLocalFabOrder(oldFabOrder);
            setFabOrderInputValue(formatFabOrder(oldFabOrder ?? ''));
            // Backend stage gate: a tagged photo is required. Re-open the modal
            // in gate mode so the user can upload one rather than just erroring.
            const data = error?.response?.data;
            if (data?.code === 'photo_required' && data?.stage) {
                setGateStage(data.stage);
                setPdfHistoryOpen(true);
            } else {
                alert(`Failed to update stage: ${data?.error || error.message}`);
            }
        } finally {
            setUpdatingStage(false);
            if (onCascadeRecalculating) onCascadeRecalculating(false);
        }
    };

    // Handle fab order change
    const handleFabOrderChange = async (newValue) => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];
        const parsedValue = newValue === '' ? null : parseFloat(newValue);

        const oldValue = localFabOrder;

        // Optimistic update
        setLocalFabOrder(parsedValue);
        setUpdatingFabOrder(true);
        if (onCascadeRecalculating) onCascadeRecalculating(true);

        try {
            console.log(`[FAB_ORDER] Updating job ${jobNumber}-${releaseNumber} from ${oldValue} to ${parsedValue}`);

            await jobsApi.updateFabOrder(jobNumber, releaseNumber, parsedValue);

            console.log(`[FAB_ORDER] Successfully updated job ${jobNumber}-${releaseNumber} to ${parsedValue}`);

            // Trigger refetch to show collision detection changes and latest state
            if (onUpdate) {
                onUpdate();
            }
        } catch (error) {
            console.error(`[FAB_ORDER] Failed to update fab order for job ${row['Job #']}-${row['Release #']}:`, error);
            // Revert on error
            setLocalFabOrder(oldValue);
            setFabOrderInputValue(formatFabOrder(oldValue ?? ''));
            alert(`Failed to update fab order: ${error.message}`);
        } finally {
            setUpdatingFabOrder(false);
            if (onCascadeRecalculating) onCascadeRecalculating(false);
        }
    };

    // Handle notes change
    const handleNotesChange = async (newValue) => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];

        const oldValue = localNotes;

        // Optimistic update
        setLocalNotes(newValue);
        setUpdatingNotes(true);

        try {
            console.log(`[NOTES] Updating job ${jobNumber}-${releaseNumber}`);

            await jobsApi.updateNotes(jobNumber, releaseNumber, newValue);

            console.log(`[NOTES] Successfully updated job ${jobNumber}-${releaseNumber}`);

            // Trigger refetch to show latest state
            if (onUpdate) {
                onUpdate();
            }
        } catch (error) {
            console.error(`[NOTES] Failed to update notes for job ${row['Job #']}-${row['Release #']}:`, error);
            // Revert on error
            setLocalNotes(oldValue);
            setNotesInputValue(oldValue ?? '');
            alert(`Failed to update notes: ${error.message}`);
        } finally {
            setUpdatingNotes(false);
        }
    };

    const handleJobCompChange = async (newValue) => {
        const oldValue = localJobComp ?? '';
        const oldStage = localStage;
        const oldFabOrder = localFabOrder;
        setLocalJobComp(newValue);
        const trimmed = newValue.trim();
        // 'X' marks install complete; a percentage means install has started.
        // Clearing the cell leaves the stage unchanged (backend does the same).
        if (trimmed.toUpperCase() === 'X') {
            setLocalStage('Install Complete');
            setLocalFabOrder(null);
            setFabOrderInputValue('');
        } else if (trimmed !== '' && !Number.isNaN(parseFloat(trimmed.replace('%', '')))) {
            setLocalStage('Install Start');
        }
        setUpdatingJobComp(true);
        try {
            await jobsApi.updateJobComp(row['Job #'], row['Release #'], newValue);
            if (onUpdate) onUpdate();
        } catch (err) {
            setLocalJobComp(oldValue);
            setJobCompInputValue(oldValue);
            setLocalStage(oldStage);
            setLocalFabOrder(oldFabOrder);
            setFabOrderInputValue(formatFabOrder(oldFabOrder ?? ''));
            alert(`Failed to update job comp: ${err.message}`);
        } finally {
            setUpdatingJobComp(false);
        }
    };

    const handleInvoicedChange = async (newValue) => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];

        const oldValue = localInvoiced ?? '';
        setLocalInvoiced(newValue);
        setUpdatingInvoiced(true);
        try {
            await jobsApi.updateInvoiced(jobNumber, releaseNumber, newValue);
            if (onUpdate) onUpdate();
        } catch (err) {
            setLocalInvoiced(oldValue);
            setInvoicedInputValue(oldValue);
            alert(`Failed to update invoiced: ${err.message}`);
        } finally {
            setUpdatingInvoiced(false);
        }
    };

    // Handle start install change from modal
    const handleStartInstallSave = async (dateValue, installer) => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];

        const oldValue = localStartInstall;

        // Optimistic update — close the modal right away; the row's cascade
        // spinner provides the in-flight feedback. Mirrors handleClearHardDate.
        // Only touch the date optimistically when one was actually provided
        // (an installer-only save passes a null date and must not clear it).
        if (dateValue) setLocalStartInstall(dateValue);
        setUpdatingStartInstall(true);
        setIsStartInstallModalOpen(false);
        if (onCascadeRecalculating) onCascadeRecalculating(true);

        try {
            console.log(`[START_INSTALL] Updating job ${jobNumber}-${releaseNumber} from ${oldValue} to ${dateValue} (installer=${installer})`);

            await jobsApi.updateStartInstall(jobNumber, releaseNumber, dateValue, installer);

            console.log(`[START_INSTALL] Successfully updated job ${jobNumber}-${releaseNumber} to ${dateValue}`);

            // Trigger refetch to show latest state
            if (onUpdate) {
                onUpdate();
            }
        } catch (error) {
            console.error(`[START_INSTALL] Failed to update start install for job ${row['Job #']}-${row['Release #']}:`, error);
            // Revert on error
            setLocalStartInstall(oldValue);
            alert(`Failed to update start install: ${error.message}`);
        } finally {
            setUpdatingStartInstall(false);
            if (onCascadeRecalculating) onCascadeRecalculating(false);
        }
    };

    // Handle ship date change from modal (independent of the install-date save)
    const handleShipDateSave = async (shipDate) => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];
        const oldValue = localShipDate;

        // Optimistic update
        setLocalShipDate(shipDate);
        try {
            await jobsApi.updateShipDate(jobNumber, releaseNumber, shipDate);
            if (onUpdate) onUpdate();
        } catch (error) {
            console.error(`[SHIP_DATE] Failed to update ship date for job ${jobNumber}-${releaseNumber}:`, error);
            setLocalShipDate(oldValue);
            alert(`Failed to update ship date: ${error.message}`);
        }
    };

    const handleSetAsap = async (installer) => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];

        setIsStartInstallModalOpen(false);
        try {
            const ok = await setAsapAndAssign(jobNumber, releaseNumber, installer);
            if (ok && onUpdate) onUpdate();
        } catch (error) {
            console.error(`[START_INSTALL] Failed to set ASAP for job ${jobNumber}-${releaseNumber}:`, error);
            alert(`Failed to set ASAP: ${error.message}`);
        }
    };

    const handleClearAsap = async () => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];

        setIsStartInstallModalOpen(false);
        try {
            await jobsApi.setStartInstallAsap(jobNumber, releaseNumber, false);
            if (onUpdate) onUpdate();
        } catch (error) {
            console.error(`[START_INSTALL] Failed to clear ASAP for job ${jobNumber}-${releaseNumber}:`, error);
            alert(`Failed to clear ASAP: ${error.message}`);
        }
    };

    // Handle clearing a hard date (revert to formula-driven)
    const handleClearHardDate = async () => {
        const jobNumber = row['Job #'];
        const releaseNumber = row['Release #'];

        const oldValue = localStartInstall;
        const oldShipDate = localShipDate;

        // Optimistic update — clearing the hard date also drops the tied ship date.
        setLocalStartInstall(null);
        setLocalShipDate(null);
        setIsStartInstallModalOpen(false);
        if (onCascadeRecalculating) onCascadeRecalculating(true);

        try {
            console.log(`[START_INSTALL] Clearing hard date for job ${jobNumber}-${releaseNumber}`);
            await jobsApi.clearStartInstallHardDate(jobNumber, releaseNumber);
            console.log(`[START_INSTALL] Successfully cleared hard date for job ${jobNumber}-${releaseNumber}`);

            if (onUpdate) {
                onUpdate();
            }
        } catch (error) {
            console.error(`[START_INSTALL] Failed to clear hard date for job ${row['Job #']}-${row['Release #']}:`, error);
            setLocalStartInstall(oldValue);
            setLocalShipDate(oldShipDate);
            alert(`Failed to clear hard date: ${error.message}`);
        } finally {
            if (onCascadeRecalculating) onCascadeRecalculating(false);
        }
    };

    // Prevent drag start from protected cells
    const handleProtectedCellMouseDown = (e) => {
        const target = e.target;

        // Allow input, textarea, select elements to work normally (don't prevent default)
        const isInputElement = target.tagName === 'INPUT' ||
            target.tagName === 'TEXTAREA' ||
            target.tagName === 'SELECT' ||
            target.closest('input') !== null ||
            target.closest('textarea') !== null ||
            target.closest('select') !== null;

        if (isInputElement) {
            // Don't prevent default for input elements - let them work normally
            e.stopPropagation();
            return;
        }

        e.stopPropagation();
        // Prevent drag from starting on these cells (but not on input elements)
        e.preventDefault();
    };

    // Drag and drop handlers
    const handleDragStart = (e) => {
        if (!isDraggable) {
            e.preventDefault();
            return;
        }

        // Check if drag started from a protected cell (Fab Order, Stage, Notes, Start install)
        const target = e.target;
        const cell = target.closest('td');

        if (cell) {
            const cellClasses = cell.className || '';
            const isFabOrderCell = cell.querySelector('input[type="text"]') !== null ||
                cell.querySelector('input[type="number"]') !== null;
            const isStartInstallCell = cell.querySelector('input[type="date"]') !== null;
            const isStageCell = cell.querySelector('select') !== null;
            const isNotesCell = cell.querySelector('textarea') !== null;
            const isEditableXCell = cell.getAttribute('data-editable-x') === 'true';

            // Also check if clicking on inputs, textareas, selects, links, or buttons anywhere
            const isInputElement = target.tagName === 'INPUT' ||
                target.tagName === 'TEXTAREA' ||
                target.tagName === 'SELECT' ||
                target.tagName === 'A' ||
                target.tagName === 'BUTTON' ||
                target.closest('input') ||
                target.closest('textarea') ||
                target.closest('select') ||
                target.closest('a') ||
                target.closest('button');

            if (isFabOrderCell || isStartInstallCell || isStageCell || isNotesCell || isEditableXCell || isInputElement) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                return false;
            }
        }

        if (onDragStart) {
            onDragStart(e, rowIndex, row);
        }
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', ''); // Required for Firefox
    };

    const handleDragOver = (e) => {
        if (!isDraggable) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (onDragOver) {
            onDragOver(e, rowIndex);
        }
    };

    const handleDragLeave = (e) => {
        if (!isDraggable) return;
        // Only trigger if we're actually leaving the row (not just moving between child elements)
        if (!e.currentTarget.contains(e.relatedTarget)) {
            // Let the parent handle clearing the drag over state
        }
    };

    const handleDrop = (e) => {
        if (!isDraggable) return;
        e.preventDefault();
        if (onDrop) {
            onDrop(e, rowIndex, row);
        }
    };

    const isDragOver = dragOverIndex === rowIndex;
    const isBeingDragged = isDragging === rowIndex;

    return (
        <>
            {/* Drop indicator line - appears above the row when dragging over */}
            {isDragOver && (
                <tr className="drop-indicator-row">
                    <td
                        colSpan={columns.length}
                        className="p-0"
                        style={{
                            height: '4px',
                            padding: '0 !important',
                            backgroundColor: 'transparent',
                        }}
                    >
                        <div
                            className="w-full h-full bg-blue-500 rounded-full"
                            style={{
                                height: '4px',
                                boxShadow: '0 2px 8px rgba(59, 130, 246, 0.5)',
                                animation: 'dropIndicatorPulse 1.5s ease-in-out infinite',
                            }}
                        ></div>
                    </td>
                </tr>
            )}
            <tr
                className={`group jl-row ${isGrayed ? 'jl-done' : ''} ${rowBgClass} transition-all duration-200 ${row._asapPropagated ? ASAP_PROPAGATED_ROW_CLASS : ''} ${isDragOver ? 'bg-blue-50 dark:bg-blue-900/30' : ''} ${isBeingDragged ? 'opacity-40 scale-[0.98] shadow-lg' : ''} ${isDragOver ? 'ring-2 ring-blue-400 ring-inset' : ''} ${isJumpToHighlight ? JUMP_TO_HIGHLIGHT_CLASS : ''}`}
                draggable={isDraggable}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragLeave={onDragLeave}
                onDrop={handleDrop}
                data-job={row['Job #']}
                data-release={row['Release #']}
            >
                {columns.map((column) => {
                    let rawValue = row[column];

                    // Format date columns
                    if (column === 'Released' || column === 'Start install' || column === 'Comp. ETA' || column === 'Ship Date') {
                        rawValue = formatDate(rawValue);
                    } else {
                        rawValue = formatCellValue(rawValue, column);
                    }

                    // Job and Description: wrap to 2 lines then truncate with ellipsis
                    const shouldWrapAndTruncate = column === 'Job' || column === 'Description';

                    // Determine if this column should allow text wrapping
                    // Paint color has its own branch (centered wrap); Notes keeps free wrap.
                    const shouldWrap = column === 'Notes';
                    const whitespaceClass = shouldWrap ? 'whitespace-normal' : 'whitespace-nowrap';

                    // Prose columns opt out; everything reaching the generic cell
                    // below is a number, date or code and takes the tabular treatment.
                    const isTextColumn = column === 'PM' || column === 'BY';

                    // Reduce padding for tight numeric columns so values like
                    // "108.00" still center instead of overflowing the cell.
                    const isReleaseNumber = column === 'Release #';
                    const isHoursColumn = column === 'Fab Hrs' || column === 'Install HRS';
                    const paddingClass = compact
                        ? 'px-0.5'
                        : (isReleaseNumber || isHoursColumn ? 'px-0.5' : 'px-2');

                    // See COLUMN_WIDTH_PERCENT in pages/JobLog.jsx for the viewport
                    // tuning + responsive plan before changing min-widths in this file.
                    if (column === 'Urgency') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} ${cellPy} whitespace-nowrap ${cellText} align-middle font-medium ${rowBgClass} text-center relative`}
                                style={{ minWidth: '230px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <StageIconRow stage={localStage} />
                            </td>
                        );
                    }

                    // Handle Stage column with editable color-coded dropdown (no banana here; see Urgency column)
                    if (column === 'Stage') {
                        // Use stage subset colors when provided, else per-stage colors
                        const getStageColors = (stageValue) => {
                            if (stageToGroup && stageGroupColors) {
                                const group = stageToGroup[stageValue] || 'FABRICATION';
                                return stageGroupColors[group] || stageGroupColors.FABRICATION;
                            }
                            return stageColors[stageValue] || stageColors['Released'];
                        };
                        const currentStageColors = getStageColors(localStage);
                        const currentOption = stageOptions.find(opt => opt.value === localStage);
                        const currentLabel = currentOption ? currentOption.label : localStage;

                        // Print fills the entire Stage cell (not a floating pill). Width
                        // comes from COLUMN_WIDTH_PERCENT — a fixed minWidth fought the
                        // lattice and left labels looking left-biased.
                        const stageCellStyle = {
                            backgroundColor: currentStageColors.light,
                            color: currentStageColors.text,
                        };

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 ${cellPy} whitespace-nowrap ${cellText} align-middle font-bold text-center relative`}
                                style={stageCellStyle}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <div className="relative w-full flex items-center justify-center">
                                    <button
                                        ref={stageTriggerRef}
                                        type="button"
                                        onClick={() => !updatingStage && setShowStageDropdown((v) => !v)}
                                        disabled={updatingStage}
                                        className={`w-full min-w-0 px-0.5 py-0 ${cellText} border border-transparent hover:border-black/10 rounded font-bold text-center leading-tight transition-all bg-transparent ${updatingStage ? 'opacity-50 cursor-wait' : ''}`}
                                        style={{ color: currentStageColors.text }}
                                    >
                                        {currentLabel}
                                    </button>
                                    {showStageDropdown && (
                                        <>
                                            <div
                                                className="fixed inset-0 z-10"
                                                onClick={() => setShowStageDropdown(false)}
                                                aria-hidden="true"
                                            />
                                            <div
                                                ref={stageListRef}
                                                className={`absolute left-1/2 -translate-x-1/2 min-w-full w-max max-w-[12rem] ${dropdownDirection === 'up' ? 'bottom-full mb-0.5' : 'top-full mt-0.5'} rounded-md border-2 border-gray-300 dark:border-slate-500 shadow-lg z-20 max-h-64 overflow-y-auto overflow-x-hidden bg-white dark:bg-slate-800 flex flex-col`}
                                            >
                                                {rotatedStageOptions.map((option) => {
                                                    const optionColors = getStageColors(option.value);
                                                    const isSelected = option.value === localStage;
                                                    return (
                                                        <button
                                                            key={option.value}
                                                            ref={isSelected ? selectedStageRef : null}
                                                            type="button"
                                                            onClick={() => {
                                                                handleStageChange(option.value);
                                                                setShowStageDropdown(false);
                                                            }}
                                                            className={`w-full px-1.5 py-1 ${cellText} font-medium text-center first:rounded-t-md last:rounded-b-md hover:brightness-95 ${isSelected ? 'ring-1 ring-inset ring-gray-400 dark:ring-slate-400' : ''}`}
                                                            style={{
                                                                backgroundColor: optionColors.light,
                                                                color: optionColors.text,
                                                                borderColor: optionColors.border
                                                            }}
                                                        >
                                                            {option.label}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </>
                                    )}
                                </div>
                            </td>
                        );
                    }

                    // Handle Fab Order column with editable input
                    if (column === 'Fab Order') {
                        const displayValue = localFabOrder === null || localFabOrder === undefined ? '—' : formatCellValue(localFabOrder, column);
                        const fabOrderGroup = stageToGroup?.[localStage] || 'FABRICATION';
                        const groupDupes = duplicateFabOrders?.get?.(fabOrderGroup);
                        const isDuplicateFabOrder = !!groupDupes && localFabOrder != null && localFabOrder >= 3 && groupDupes.has(localFabOrder);
                        const dupColor = isDuplicateFabOrder ? (stageGroupDupColors?.[fabOrderGroup] || '#f97316') : null;
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                // Tight cell pad — fab order is a short numeric; full
                                // paddingClass + w-full input ballooned the hover chrome.
                                className={`px-0.5 ${cellPy} whitespace-nowrap ${cellText} align-middle font-medium ${isDuplicateFabOrder ? '' : rowBgClass} text-center`}
                                style={isDuplicateFabOrder ? { backgroundColor: dupColor } : undefined}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <input
                                    type="text"
                                    inputMode="numeric"
                                    value={fabOrderInputValue}
                                    onChange={(e) => setFabOrderInputValue(e.target.value)}
                                    onBlur={(e) => {
                                        const newValue = e.target.value.trim();
                                        if (newValue === '') {
                                            // User cleared the field
                                            if (localFabOrder !== null && localFabOrder !== undefined) {
                                                handleFabOrderChange('');
                                            } else {
                                                // Already empty, just sync the input
                                                setFabOrderInputValue('');
                                            }
                                        } else {
                                            const parsedValue = parseFloat(newValue);
                                            if (!isNaN(parsedValue) && isFinite(parsedValue)) {
                                                // Valid number - check if it changed
                                                const currentValue = localFabOrder === null || localFabOrder === undefined ? null : localFabOrder;
                                                if (parsedValue !== currentValue) {
                                                    handleFabOrderChange(newValue);
                                                }
                                            } else {
                                                // Invalid input, revert
                                                setFabOrderInputValue(formatFabOrder(localFabOrder ?? ''));
                                            }
                                        }
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                            e.target.blur();
                                        } else if (e.key === 'Escape') {
                                            setFabOrderInputValue(formatFabOrder(localFabOrder ?? ''));
                                            e.target.blur();
                                        }
                                    }}
                                    disabled={updatingFabOrder || isGrayed}
                                    size={6}
                                    className={`mx-auto block max-w-full px-0.5 py-0 ${cellText} ${cellMono} rounded-sm focus:outline-none ${isDuplicateFabOrder ? 'text-white font-bold bg-transparent border border-transparent' : `${quietInput} text-ink`} text-center tabular-nums ${updatingFabOrder ? 'opacity-50 cursor-wait' : ''} ${isGrayed ? 'opacity-50 cursor-not-allowed' : ''}`}
                                    placeholder="—"
                                    style={(() => {
                                        // Wide enough for the 80.555 placeholder (3dp) without a full-cell pill.
                                        const w = compact ? '2.75rem' : '3.25rem';
                                        const base = { width: w, minWidth: w, maxWidth: '100%' };
                                        return isDuplicateFabOrder ? { ...base, backgroundColor: dupColor } : base;
                                    })()}
                                />
                            </td>
                        );
                    }

                    // Handle Notes column with editable textarea
                    if (column === 'Notes') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`relative ${paddingClass} ${cellPy} ${cellText} align-middle font-medium ${rowBgClass} text-center whitespace-normal`}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <textarea
                                    value={notesInputValue}
                                    onChange={(e) => setNotesInputValue(e.target.value)}
                                    onBlur={(e) => {
                                        const newValue = e.target.value.trim();
                                        if (newValue !== (localNotes ?? '')) {
                                            handleNotesChange(newValue);
                                        }
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Escape') {
                                            setNotesInputValue(localNotes ?? '');
                                            e.target.blur();
                                        } else if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            e.target.blur();
                                        }
                                    }}
                                    disabled={updatingNotes}
                                    className={`w-full px-0.5 py-0.5 ${cellText} ${quietInput} rounded focus:outline-none text-ink text-center resize-none ${updatingNotes ? 'opacity-50 cursor-wait' : ''}`}
                                    placeholder="—"
                                    rows={2}
                                />
                                {/* The notes-history glyph that used to sit here is gone: the
                                    history is the release hub's Notes rail now, reached from
                                    Description like everything else. The cell keeps showing —
                                    and editing — the current note. */}
                            </td>
                        );
                    }

                    // Handle Job Comp column - editable text input
                    if (column === 'Job Comp') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                data-editable-x="true"
                                className={`${paddingClass} ${cellPy} whitespace-nowrap ${cellText} align-middle font-medium ${rowBgClass} text-center`}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <input
                                    type="text"
                                    value={jobCompInputValue}
                                    onChange={(e) => setJobCompInputValue(e.target.value)}
                                    onBlur={(e) => {
                                        const newValue = e.target.value.trim();
                                        if (newValue !== (localJobComp ?? '')) {
                                            handleJobCompChange(newValue);
                                        } else {
                                            setJobCompInputValue(localJobComp ?? '');
                                        }
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') e.target.blur();
                                        if (e.key === 'Escape') {
                                            setJobCompInputValue(localJobComp ?? '');
                                            e.target.blur();
                                        }
                                    }}
                                    disabled={updatingJobComp}
                                    className={`w-full min-w-0 px-1 py-0.5 ${cellText} ${cellMono} font-semibold ${quietInput} rounded focus:outline-none text-ink text-center ${updatingJobComp ? 'opacity-50 cursor-wait' : ''}`}
                                    placeholder="—"
                                />
                            </td>
                        );
                    }

                    // Handle Invoiced column - editable text input
                    if (column === 'Invoiced') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                data-editable-x="true"
                                className={`${paddingClass} ${cellPy} whitespace-nowrap ${cellText} align-middle font-medium ${rowBgClass} text-center`}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <input
                                    type="text"
                                    value={invoicedInputValue}
                                    onChange={(e) => setInvoicedInputValue(e.target.value)}
                                    onBlur={(e) => {
                                        const newValue = e.target.value.trim();
                                        if (newValue !== (localInvoiced ?? '')) {
                                            handleInvoicedChange(newValue);
                                        } else {
                                            setInvoicedInputValue(localInvoiced ?? '');
                                        }
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') e.target.blur();
                                        if (e.key === 'Escape') {
                                            setInvoicedInputValue(localInvoiced ?? '');
                                            e.target.blur();
                                        }
                                    }}
                                    disabled={updatingInvoiced}
                                    className={`w-full min-w-0 px-1 py-0.5 ${cellText} ${cellMono} font-semibold ${quietInput} rounded focus:outline-none text-ink text-center ${updatingInvoiced ? 'opacity-50 cursor-wait' : ''}`}
                                    placeholder="—"
                                />
                            </td>
                        );
                    }

                    // Handle Start install column with clickable cell that opens modal
                    if (column === 'Start install') {
                        // N5: at shipping stages hard dates stay washed white (also covers optimistic
                        // save before refetch brings back start_install_no_color).
                        const atShippingStage = localStage === 'Ship Planning' || localStage === 'Ship Complete';
                        const isAsap = !atShippingStage && row['start_install_asap'] === true;
                        const displayValue = isAsap ? 'ASAP' : formatDate(localStartInstall);
                        // A no-color date (N5 shipping wash / complete-zone neutralize) shows plainly —
                        // not the green/yellow hard-date treatment.
                        const isNoColor = atShippingStage || row['start_install_no_color'] === true;
                        // Hard date is when start_install_formulaTF is explicitly false and there's a date value
                        const isHardDate = !isAsap && !isNoColor && row['start_install_formulaTF'] === false && localStartInstall;
                        // Formula date is when start_install_formulaTF is true or formula starts with '='
                        const isFormulaDate = !isAsap && (row['start_install_formulaTF'] === true || (row['start_install_formula'] && row['start_install_formula'].startsWith('=')));
                        // IMPORTANT: avoid conflicting bg-* utilities (Tailwind utility order, not class string order,
                        // determines the winner). If we include both rowBgClass and bg-red-500, the row bg can win,
                        // leaving white text on a light background (looks blank until hover).
                        // Hard dates compare to today's LOCAL date (toISOString would shift to UTC).
                        const now = new Date();
                        const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
                        const installDay = String(localStartInstall ?? '').split('T')[0];
                        const isHardDatePast = isHardDate && installDay < todayStr;
                        let startInstallBgClass;
                        if (isAsap) {
                            startInstallBgClass = 'jl-flag jl-flag-red';
                        } else if (isHardDatePast) {
                            startInstallBgClass = 'jl-flag jl-flag-amber';
                        } else if (isHardDate) {
                            startInstallBgClass = 'jl-flag jl-flag-green';
                        } else {
                            startInstallBgClass = `${rowBgClass} text-ink`;
                        }

                        const titleText = isAsap
                            ? 'ASAP — release will jump from Paint Complete to Shipping Planning. Click to edit.'
                            : isFormulaDate
                                ? `${displayValue} (Formula-driven - Click to set hard date)`
                                : `${displayValue} - Click to edit`;

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} ${cellPy} whitespace-nowrap ${cellText} ${cellMono} align-middle font-medium ${startInstallBgClass} text-center cursor-pointer transition-colors ${updatingStartInstall ? 'opacity-50' : ''}`}
                                onClick={() => !updatingStartInstall && setIsStartInstallModalOpen(true)}
                                title={titleText}
                            >
                                <div className="leading-tight text-center">{displayValue}</div>
                                <div className={`text-jl-3 leading-tight text-center ${isAsap || isHardDate || isHardDatePast ? 'opacity-90 font-medium' : 'text-ink-2'}`}>
                                    {row['installer'] || '—'}
                                </div>
                            </td>
                        );
                    }

                    // Handle Ship Date column: clickable cell that opens the same modal.
                    // The ship date is a derived milestone (~1 biz day before Start install),
                    // so its cell MIRRORS the paired Start install cell's color exactly — the
                    // two columns must always read the same. Key every branch on the INSTALL
                    // date/flags, not the ship date's own past/future: ship crosses "today" a
                    // day earlier than install, so keying on shipDay would show yellow while
                    // install is still green. ASAP propagates red; formula/no-color/no-date
                    // fall through to neutral, matching Start install above.
                    if (column === 'Ship Date') {
                        const atShippingStage = localStage === 'Ship Planning' || localStage === 'Ship Complete';
                        const isAsap = !atShippingStage && row['start_install_asap'] === true;
                        // Show "ASAP" instead of the underlying date, matching the Start install cell.
                        const displayValue = isAsap ? 'ASAP' : formatDate(localShipDate);
                        // N5: wash at shipping stages (mirrors Start install cell).
                        const isNoColor = atShippingStage || row['start_install_no_color'] === true;
                        const hasDate = !!localShipDate;
                        // Same hard-date test the Start install cell uses.
                        const isHardDate = !isAsap && !isNoColor && row['start_install_formulaTF'] === false && localStartInstall;
                        const isHardDatePast = isHardDate && toYmd(localStartInstall) < localTodayStr();
                        let shipBgClass;
                        if (isAsap) {
                            shipBgClass = 'jl-flag jl-flag-red';
                        } else if (!hasDate || isNoColor || !isHardDate) {
                            shipBgClass = `${rowBgClass} text-ink`;
                        } else if (isHardDatePast) {
                            shipBgClass = 'jl-flag jl-flag-amber';
                        } else {
                            shipBgClass = 'jl-flag jl-flag-green';
                        }
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} ${cellPy} whitespace-nowrap ${cellText} ${cellMono} align-middle font-medium ${shipBgClass} text-center cursor-pointer transition-colors ${updatingStartInstall ? 'opacity-50' : ''}`}
                                onClick={() => !updatingStartInstall && setIsStartInstallModalOpen(true)}
                                title={updatingStartInstall
                                    ? 'Recalculating dates…'
                                    : `${displayValue} — Click to edit`}
                            >
                                <div className="leading-tight text-center">{displayValue}</div>
                            </td>
                        );
                    }

                    // Material order status — a banana glyph (green/amber/red) when the
                    // release has orders, blank otherwise. Click opens the modal at the
                    // Materials Ordered section.
                    if (column === 'Mat. Ord.') {
                        const matStatus = row['Mat. Ord.'];
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} ${cellPy} ${cellText} align-middle ${rowBgClass} text-center ${matStatus ? 'cursor-pointer hover:bg-accent-50 dark:hover:bg-slate-600 transition-colors' : ''}`}
                                onClick={matStatus ? () => openHub('details', { scrollToMaterials: true }) : undefined}
                            >
                                <div className="flex items-center justify-center">
                                    <MaterialOrderBadge status={matStatus} />
                                </div>
                            </td>
                        );
                    }

                    // For Job and Description, show full value in tooltip
                    const tooltipValue = shouldWrapAndTruncate ? rawValue : rawValue;

                    // Paint color — multi-line, explicitly centered (generic branch
                    // left multi-line prose looking left-biased in a narrow column).
                    if (column === 'Paint color') {
                        const paintText = rawValue == null || rawValue === '—' ? '—' : String(rawValue);
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 ${cellPy} text-jl-2 align-middle ${rowBgClass} text-center text-ink`}
                                title={paintText === '—' ? undefined : paintText}
                            >
                                <div
                                    className="mx-auto w-full text-center leading-tight"
                                    style={{
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        textAlign: 'center',
                                    }}
                                >
                                    {paintText}
                                </div>
                            </td>
                        );
                    }

                    // Job column — plain text. Width comes from COLUMN_WIDTH_PERCENT
                    // (no fixed px) so the lattice stays even with the rest of the table.
                    if (column === 'Job') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-1 ${cellPy} text-jl-2 align-middle ${rowBgClass} text-center text-ink`}
                                title={tooltipValue}
                            >
                                <div
                                    className="mx-auto text-center"
                                    style={{
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical',
                                        overflow: 'hidden',
                                        textOverflow: 'clip',
                                        lineHeight: '1.2',
                                        textAlign: 'center',
                                    }}
                                >
                                    {rawValue}
                                </div>
                            </td>
                        );
                    }

                    // Description column — the row's one hyperlink. Opens the release
                    // hub, which carries both the job details and the drawings/photos
                    // hub the Release # cell used to reach on its own.
                    if (column === 'Description') {
                        const hasText = rawValue != null && String(rawValue).trim() !== '';
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-1 ${cellPy} ${cellText} align-middle font-medium ${rowBgClass} text-center cursor-pointer hover:bg-accent-50 dark:hover:bg-slate-600 transition-colors`}
                                title={hasText ? `${tooltipValue} — click to open` : 'Click to open'}
                                onClick={() => openHub('details')}
                            >
                                <div
                                    className="mx-auto text-center"
                                    style={{
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical',
                                        overflow: 'hidden',
                                        textOverflow: 'clip',
                                        lineHeight: '1.2',
                                        textAlign: 'center',
                                    }}
                                >
                                    {/* The handoff renders Description as bold dark text
                                        because there the whole row is clickable. Here it
                                        is the row's ONLY way into the release, so it keeps
                                        a link's affordance — token accent, not raw blue. */}
                                    <span className="font-semibold text-brand hover:underline">
                                        {hasText ? rawValue : '—'}
                                    </span>
                                </div>
                            </td>
                        );
                    }

                    // Release # column — plain text. The drawing-version hub it used
                    // to open now lives on the release hub's Drawings & Photos tab,
                    // reached from Description along with everything else.
                    if (column === 'Release #') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} ${cellPy} ${cellText} ${cellMono} align-middle font-semibold ${rowBgClass} text-center text-ink`}
                            >
                                <div className="flex items-center justify-center">
                                    {rawValue}
                                </div>
                            </td>
                        );
                    }

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            // Numbers and dates ride mono; free text (Job Name, Paint
                            // color, Notes) stays in the UI face at the secondary size.
                            // Body values use primary ink (print is black). Secondary
                            // size only for free-text support columns (Paint / PM / BY).
                            className={`${paddingClass} ${cellPy} ${isTextColumn ? 'text-jl-2 text-ink' : `${cellText} ${cellMono} text-ink`} align-middle ${rowBgClass} text-center ${isHoursColumn ? 'tabular-nums' : ''} ${shouldWrapAndTruncate
                                ? ''
                                : whitespaceClass
                                }`}
                            title={tooltipValue}
                        >
                            {shouldWrapAndTruncate ? (
                                <div
                                    className="mx-auto text-center"
                                    style={{
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        lineHeight: '1.2',
                                        textAlign: 'center',
                                    }}
                                >
                                    {rawValue}
                                </div>
                            ) : (
                                <span className={`block w-full text-center ${isHoursColumn ? 'tabular-nums' : ''}`}>{rawValue}</span>
                            )}
                        </td>
                    );
                })}
                {showActions && (canEditRowFields || isAdmin) && (
                    <td
                        className={`px-1 ${cellPy} text-center align-middle ${rowBgClass} w-8 relative`}
                        style={{ width: '32px' }}
                    >
                        <button
                            onClick={() => setShowActionMenu(v => !v)}
                            className="text-gray-600 dark:text-slate-400 hover:text-gray-900 dark:hover:text-slate-100 font-bold text-lg"
                            title="Actions"
                        >
                            ⋯
                        </button>
                        {showActionMenu && (
                            <>
                                <div
                                    className="fixed inset-0 z-10"
                                    onClick={() => setShowActionMenu(false)}
                                />
                                <ul className="absolute right-0 z-20 bg-white dark:bg-slate-700 shadow-lg rounded border border-gray-200 dark:border-slate-600">
                                    {onUnarchive ? (
                                        isAdmin ? (
                                            <li
                                                onClick={handleUnarchiveRow}
                                                className="px-4 py-2 text-sm text-blue-600 dark:text-blue-400 hover:bg-gray-100 dark:hover:bg-slate-600 cursor-pointer whitespace-nowrap"
                                            >
                                                Unarchive
                                            </li>
                                        ) : null
                                    ) : (
                                        <>
                                            {canEditRowFields && (
                                                <li
                                                    onClick={handleOpenRowEdit}
                                                    className="px-4 py-2 text-sm text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-600 cursor-pointer whitespace-nowrap"
                                                >
                                                    Edit row
                                                </li>
                                            )}
                                            {isAdmin && (
                                                <li
                                                    onClick={handleDeleteRow}
                                                    className="px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-slate-600 cursor-pointer whitespace-nowrap"
                                                >
                                                    Delete row
                                                </li>
                                            )}
                                        </>
                                    )}
                                </ul>
                            </>
                        )}
                    </td>
                )}
            </tr>
            <ReleaseHubModal
                isOpen={isModalOpen}
                onClose={() => { setIsModalOpen(false); setModalScrollToMaterials(false); }}
                job={row}
                releaseId={row.id}
                viewerUrl={row.viewer_url}
                initialTab={hubTab}
                scrollToMaterials={modalScrollToMaterials}
                onOrdersChanged={refreshMaterialSummary}
                onNotesChanged={(notes) => {
                    setLocalNotes(notes);
                    setNotesInputValue(notes ?? '');
                }}
                onOpenVersion={(vid, mode) => {
                    setIsModalOpen(false);
                    setPdfMarkupVersionId(vid);
                    setPdfMarkupMode(canMarkup ? mode : 'view');
                    setPdfMarkupOpen(true);
                }}
            />
            <StartInstallDateModal
                isOpen={isStartInstallModalOpen}
                onClose={() => setIsStartInstallModalOpen(false)}
                currentDate={localStartInstall}
                currentShipDate={localShipDate}
                currentInstaller={row['installer']}
                onSave={handleStartInstallSave}
                onSaveShipDate={handleShipDateSave}
                onClearHardDate={handleClearHardDate}
                onSetAsap={handleSetAsap}
                onClearAsap={handleClearAsap}
                jobNumber={row['Job #']}
                releaseNumber={row['Release #']}
                startInstallFormulaTF={row['start_install_formulaTF']}
                isAsap={row['start_install_asap'] === true}
                // Use localStage so Store→Ship Planning (before parent refetch) still
                // opens the modal in N5 manual/Break mode, not estimated Link.
                stage={localStage}
            />
            <PdfMarkupModal
                isOpen={pdfMarkupOpen}
                releaseId={row.id}
                versionId={pdfMarkupVersionId}
                mode={pdfMarkupMode}
                onClose={() => setPdfMarkupOpen(false)}
            />
            {/* Stage-photo gate only. Browsing drawings goes through the release
                hub's Drawings & Photos tab; this stays a focused confirm dialog. */}
            <PdfVersionHistoryModal
                isOpen={pdfHistoryOpen}
                releaseId={row.id}
                title={`${row['Job #']}-${row['Release #']}`}
                viewerUrl={row.viewer_url}
                gateStage={gateStage}
                onConfirmStage={() => {
                    const stageToApply = gateStage;
                    setPdfHistoryOpen(false);
                    setGateStage(null);
                    applyStageChange(stageToApply);
                }}
                onClose={() => { setPdfHistoryOpen(false); setGateStage(null); }}
                onOpenVersion={(vid, mode) => {
                    setPdfHistoryOpen(false);
                    setGateStage(null);
                    setPdfMarkupVersionId(vid);
                    setPdfMarkupMode(canMarkup ? mode : 'view');
                    setPdfMarkupOpen(true);
                }}
            />
            {showEditModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 max-w-2xl w-full mx-4">
                        <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 mb-4">
                            Edit Row — {row['Job #']}-{row['Release #']}
                        </h2>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                            {EDITABLE_COLUMNS.map((col) => (
                                <div key={col.field}>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">
                                        {col.label}
                                    </label>
                                    <input
                                        type={col.type === 'date' ? 'date' : col.type === 'number' ? 'number' : 'text'}
                                        step={col.type === 'number' ? '0.01' : undefined}
                                        value={fieldValues[col.field] ?? ''}
                                        onChange={(e) => setFieldValues(prev => ({ ...prev, [col.field]: e.target.value }))}
                                        className="w-full px-3 py-2 border border-gray-400 dark:border-slate-700 rounded-md bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                                    />
                                </div>
                            ))}
                        </div>
                        <div className="flex gap-2">
                            <button
                                onClick={handleSaveEdit}
                                disabled={saving}
                                className="flex-1 bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {saving ? 'Saving...' : 'Save'}
                            </button>
                            <button
                                onClick={() => setShowEditModal(false)}
                                className="flex-1 bg-gray-300 dark:bg-slate-600 hover:bg-gray-400 dark:hover:bg-slate-500 text-gray-900 dark:text-slate-100 font-medium py-2 px-4 rounded-md"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}

