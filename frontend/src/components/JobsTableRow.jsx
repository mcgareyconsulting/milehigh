import React, { useState, useEffect } from 'react';
import { jobsApi } from '../services/jobsApi';
import { JUMP_TO_HIGHLIGHT_CLASS } from '../constants/jumpToHighlight';
import { JobDetailsModal } from './JobDetailsModal';
import { StartInstallDateModal } from './StartInstallDateModal';
import { BananaIcon } from './BananaIcon';

export function JobsTableRow({ row, columns, formatCellValue, formatDate, rowIndex, onDragStart, onDragOver, onDragLeave, onDrop, isDragging, dragOverIndex, onUpdate, stageToGroup, stageGroupColors, isJumpToHighlight, isAdmin = false, onDelete = null }) {
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isStartInstallModalOpen, setIsStartInstallModalOpen] = useState(false);
    const [showActionMenu, setShowActionMenu] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [editField, setEditField] = useState('');
    const [editValue, setEditValue] = useState('');
    const [saving, setSaving] = useState(false);

    // Check if row should be grayed (Complete status or both Job Comp and Invoiced are X)
    const isComplete = row['Stage'] === 'Complete';

    // Row is draggable (disabled for now)
    const isDraggable = false;

    // Stage options with simplified names for display (in progression order)
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Cut start', label: 'Cut start' },
        { value: 'Material Ordered', label: 'Material Ordered' },
        { value: 'Fit Up Complete.', label: 'Fitup comp' },
        { value: 'Welded', label: 'Welded' },
        { value: 'Welded QC', label: 'Welded QC' },
        { value: 'Paint complete', label: 'Paint comp' },
        { value: 'Hold', label: 'Hold' },
        { value: 'Store at MHMW for shipping', label: 'Store' },
        { value: 'Shipping planning', label: 'Ship plan' },
        { value: 'Shipping completed', label: 'Ship comp' },
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
        'Cut start': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Fit Up Complete.': {
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Welded QC': {
            light: 'rgb(254 249 195)', // yellow-100
            base: 'rgb(234 179 8)', // yellow-500
            dark: 'rgb(202 138 4)', // yellow-600
            text: 'rgb(133 77 14)', // yellow-800
            border: 'rgb(253 224 71)', // yellow-300
            className: 'bg-yellow-100 text-yellow-800 border-yellow-300'
        },
        'Paint complete': {
            light: 'rgb(209 250 229)', // emerald-100 (green)
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Store at MHMW for shipping': {
            light: 'rgb(209 250 229)', // emerald-100 (green)
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Shipping planning': {
            light: 'rgb(209 250 229)', // emerald-100 (green)
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Shipping completed': {
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
        'Welded': {
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

    /**
     * Urgency banana count and default color by stage / stage group.
     * FAB: 1 banana (Cut/Material Ordered=green, Fitup/Welded=yellow, Released=gray, Hold=red).
     * Ready to Ship: 2 bananas (Welded QC=green, rest=yellow).
     * Complete: 3 bananas (Complete=gray, Ship comp=green).
     */
    const getBananaCountAndDefault = (stage, stageToGroupMap) => {
        const group = stageToGroupMap && stageToGroupMap[stage] ? stageToGroupMap[stage] : 'FABRICATION';
        if (group === 'FABRICATION') {
            const colorMap = {
                'Cut start': 'green',
                'Material Ordered': 'green',
                'Fit Up Complete.': 'yellow',
                'Welded': 'yellow',
                'Released': 'gray',
                'Hold': 'red',
            };
            return { count: 1, defaultColor: colorMap[stage] || 'gray' };
        }
        if (group === 'READY_TO_SHIP') {
            const colorMap = {
                'Welded QC': 'green',
                'Paint complete': 'yellow',
                'Store at MHMW for shipping': 'yellow',
                'Shipping planning': 'yellow',
            };
            return { count: 2, defaultColor: colorMap[stage] || 'yellow' };
        }
        if (group === 'COMPLETE') {
            const colorMap = {
                'Complete': 'gray',
                'Shipping completed': 'green',
            };
            return { count: 3, defaultColor: colorMap[stage] || 'gray' };
        }
        return { count: 1, defaultColor: 'gray' };
    };

    // Local state for stage
    const [localStage, setLocalStage] = useState(row['Stage'] || 'Released');
    const [updatingStage, setUpdatingStage] = useState(false);

    // Local state for fab order
    const [localFabOrder, setLocalFabOrder] = useState(row['Fab Order'] ?? '');
    const [updatingFabOrder, setUpdatingFabOrder] = useState(false);
    const [fabOrderInputValue, setFabOrderInputValue] = useState(row['Fab Order'] ?? '');

    // Local state for notes
    const [localNotes, setLocalNotes] = useState(row['Notes'] ?? '');
    const [updatingNotes, setUpdatingNotes] = useState(false);
    const [notesInputValue, setNotesInputValue] = useState(row['Notes'] ?? '');

    // Local state for start install
    const [localStartInstall, setLocalStartInstall] = useState(row['Start install'] ?? null);
    const [updatingStartInstall, setUpdatingStartInstall] = useState(false);

    // Local state for banana color
    const [localBananaColor, setLocalBananaColor] = useState(row['Banana Color'] || null);
    const [updatingBananaColor, setUpdatingBananaColor] = useState(false);
    const [showStageDropdown, setShowStageDropdown] = useState(false);

    // Local state for Job Comp and Invoiced (editable text)
    const [localJobComp, setLocalJobComp] = useState(row['Job Comp'] ?? '');
    const [localInvoiced, setLocalInvoiced] = useState(row['Invoiced'] ?? '');
    const [jobCompInputValue, setJobCompInputValue] = useState(row['Job Comp'] ?? '');
    const [invoicedInputValue, setInvoicedInputValue] = useState(row['Invoiced'] ?? '');
    const [updatingJobComp, setUpdatingJobComp] = useState(false);
    const [updatingInvoiced, setUpdatingInvoiced] = useState(false);

    // Editable columns for admin edit modal
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

    // Handlers for edit modal
    const handleEditColumn = (field) => {
        const col = EDITABLE_COLUMNS.find(c => c.field === field);
        if (!col) return;

        const displayLabel = col.label;
        const currentValue = row[displayLabel] || '';

        setEditField(field);
        setEditValue(currentValue);
        setShowActionMenu(false);
        setShowEditModal(true);
    };

    const handleSaveEdit = async () => {
        if (!editField || editValue === '') {
            setShowEditModal(false);
            return;
        }

        setSaving(true);
        try {
            await jobsApi.updateJobColumn(row['Job #'], row['Release #'], editField, editValue);
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

    // Sync local state when row data changes (e.g., on refresh)
    useEffect(() => {
        setLocalStage(row['Stage'] || 'Released');
        setLocalFabOrder(row['Fab Order'] ?? '');
        setFabOrderInputValue(row['Fab Order'] ?? '');
        setLocalNotes(row['Notes'] ?? '');
        setNotesInputValue(row['Notes'] ?? '');
        setLocalStartInstall(row['Start install'] ?? null);
        setLocalBananaColor(row['Banana Color'] || null);
        setLocalJobComp(row['Job Comp'] ?? '');
        setLocalInvoiced(row['Invoiced'] ?? '');
        setJobCompInputValue(row['Job Comp'] ?? '');
        setInvoicedInputValue(row['Invoiced'] ?? '');
    }, [row['Stage'], row['Fab Order'], row['Notes'], row['Start install'], row['Banana Color'], row['Job Comp'], row['Invoiced']]);

    const jobCompIsX = (localJobComp || '').toString().trim().toUpperCase() === 'X';
    const invoicedIsX = (localInvoiced || '').toString().trim().toUpperCase() === 'X';
    const isBothX = jobCompIsX && invoicedIsX;
    const isGrayed = isComplete || isBothX;
    const rowBgClass = isGrayed ? 'bg-gray-300 dark:bg-slate-600' : (rowIndex % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-blue-100 dark:bg-slate-700/80');

    // Handle stage change
    const handleStageChange = async (newStage) => {
        const oldStage = localStage;
        const oldBananaColor = localBananaColor;
        setLocalStage(newStage); // Optimistic update
        // Auto-flag Hold as urgent (red banana)
        if (newStage === 'Hold') {
            setLocalBananaColor('red');
        }
        setUpdatingStage(true);

        try {
            const jobNumber = row['Job #'];
            const releaseNumber = row['Release #'];

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
            setLocalBananaColor(oldBananaColor);
            alert(`Failed to update stage: ${error.message}`);
        } finally {
            setUpdatingStage(false);
        }
    };

    // Handle banana color change
    const handleBananaColorChange = async (newColor) => {
        const oldColor = localBananaColor;
        setLocalBananaColor(newColor); // Optimistic update
        setUpdatingBananaColor(true);

        try {
            const jobNumber = row['Job #'];
            const releaseNumber = row['Release #'];

            console.log(`[BANANA] Updating job ${jobNumber}-${releaseNumber} banana color from ${oldColor} to ${newColor}`);

            await jobsApi.updateBananaColor(jobNumber, releaseNumber, newColor);

            console.log(`[BANANA] Successfully updated job ${jobNumber}-${releaseNumber} banana color to ${newColor}`);

            // Trigger refetch to show latest state
            if (onUpdate) {
                onUpdate();
            }
        } catch (error) {
            console.error(`[BANANA] Failed to update banana color for job ${row['Job #']}-${row['Release #']}:`, error);
            // Revert on error
            setLocalBananaColor(oldColor);
            alert(`Failed to update banana color: ${error.message}`);
        } finally {
            setUpdatingBananaColor(false);
        }
    };

    // Handle fab order change
    const handleFabOrderChange = async (newValue) => {
        const oldValue = localFabOrder;
        const parsedValue = newValue === '' ? null : parseFloat(newValue);

        // Optimistic update
        setLocalFabOrder(parsedValue);
        setUpdatingFabOrder(true);

        try {
            const jobNumber = row['Job #'];
            const releaseNumber = row['Release #'];

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
            setFabOrderInputValue(oldValue === null || oldValue === undefined ? '' : String(oldValue));
            alert(`Failed to update fab order: ${error.message}`);
        } finally {
            setUpdatingFabOrder(false);
        }
    };

    // Handle notes change
    const handleNotesChange = async (newValue) => {
        const oldValue = localNotes;

        // Optimistic update
        setLocalNotes(newValue);
        setUpdatingNotes(true);

        try {
            const jobNumber = row['Job #'];
            const releaseNumber = row['Release #'];

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
        setLocalJobComp(newValue);
        setUpdatingJobComp(true);
        try {
            await jobsApi.updateJobComp(row['Job #'], row['Release #'], newValue);
            if (onUpdate) onUpdate();
        } catch (err) {
            setLocalJobComp(oldValue);
            setJobCompInputValue(oldValue);
            alert(`Failed to update job comp: ${err.message}`);
        } finally {
            setUpdatingJobComp(false);
        }
    };

    const handleInvoicedChange = async (newValue) => {
        const oldValue = localInvoiced ?? '';
        setLocalInvoiced(newValue);
        setUpdatingInvoiced(true);
        try {
            await jobsApi.updateInvoiced(row['Job #'], row['Release #'], newValue);
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
    const handleStartInstallSave = async (dateValue, isHardDate) => {
        if (!isHardDate) {
            // Not a hard date, just close modal
            setIsStartInstallModalOpen(false);
            return;
        }

        const oldValue = localStartInstall;
        const oldBananaColor = localBananaColor;

        // Optimistic update
        setLocalStartInstall(dateValue);
        // Auto-flag hard dates as urgent (red banana) when a date is set
        if (dateValue) {
            setLocalBananaColor('red');
        }
        setUpdatingStartInstall(true);

        try {
            const jobNumber = row['Job #'];
            const releaseNumber = row['Release #'];

            console.log(`[START_INSTALL] Updating job ${jobNumber}-${releaseNumber} from ${oldValue} to ${dateValue} (hard date: ${isHardDate})`);

            await jobsApi.updateStartInstall(jobNumber, releaseNumber, dateValue, isHardDate);

            console.log(`[START_INSTALL] Successfully updated job ${jobNumber}-${releaseNumber} to ${dateValue}`);

            // Close modal
            setIsStartInstallModalOpen(false);

            // Trigger refetch to show latest state
            if (onUpdate) {
                onUpdate();
            }
        } catch (error) {
            console.error(`[START_INSTALL] Failed to update start install for job ${row['Job #']}-${row['Release #']}:`, error);
            // Revert on error
            setLocalStartInstall(oldValue);
            setLocalBananaColor(oldBananaColor);
            alert(`Failed to update start install: ${error.message}`);
        } finally {
            setUpdatingStartInstall(false);
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
                className={`${rowBgClass} hover:bg-gray-100 dark:hover:bg-slate-600 transition-all duration-200 border-b border-gray-300 dark:border-slate-600 ${isDragOver ? 'bg-blue-50 dark:bg-blue-900/30' : ''} ${isBeingDragged ? 'opacity-40 scale-[0.98] shadow-lg' : ''} ${isDragOver ? 'ring-2 ring-blue-400 ring-inset' : ''} ${isJumpToHighlight ? JUMP_TO_HIGHLIGHT_CLASS : ''}`}
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
                    if (column === 'Released' || column === 'Start install' || column === 'Comp. ETA') {
                        rawValue = formatDate(rawValue);
                    } else {
                        rawValue = formatCellValue(rawValue, column);
                    }

                    // Job and Description: wrap to 2 lines then truncate with ellipsis
                    const shouldWrapAndTruncate = column === 'Job' || column === 'Description';

                    // Determine if this column should allow text wrapping
                    const shouldWrap = column === 'Notes' || column === 'Paint color';
                    const whitespaceClass = shouldWrap ? 'whitespace-normal' : 'whitespace-nowrap';

                    // Reduce padding for Release # column
                    const isReleaseNumber = column === 'Release #';
                    const paddingClass = isReleaseNumber ? 'px-1' : 'px-2';


                    // Urgency column: stage-based banana count + color; toggleable to red (except Hold)
                    if (column === 'Urgency') {
                        const { count: bananaCount, defaultColor: stageDefaultColor } = getBananaCountAndDefault(localStage, stageToGroup);
                        const isHold = localStage === 'Hold';
                        const effectiveColor = isHold ? 'red' : (localBananaColor === 'red' ? 'red' : stageDefaultColor);
                        const isUrgencyToggleable = !isHold && !updatingBananaColor;

                        const bananaChipClass = effectiveColor === 'red'
                            ? 'bg-red-100 dark:bg-red-900/50 border-red-300 dark:border-red-700 ring-2 ring-red-300 dark:ring-red-700'
                            : effectiveColor === 'yellow'
                                ? 'bg-yellow-100 dark:bg-yellow-900/40 border-yellow-300 dark:border-yellow-700 ring-1 ring-yellow-200 dark:ring-yellow-700'
                                : effectiveColor === 'green'
                                    ? 'bg-emerald-100 dark:bg-emerald-900/40 border-emerald-300 dark:border-emerald-700 ring-1 ring-emerald-200 dark:ring-emerald-700'
                                    : effectiveColor === 'gray'
                                        ? 'bg-gray-100 dark:bg-slate-600 border-gray-300 dark:border-slate-500 ring-1 ring-gray-200 dark:ring-slate-500'
                                        : 'bg-white dark:bg-slate-700 border-gray-300 dark:border-slate-500';
                        const bananaHoverClass = isUrgencyToggleable ? 'hover:brightness-[0.98]' : '';

                        const handleUrgencyClick = () => {
                            if (!isUrgencyToggleable) return;
                            if (effectiveColor === 'red') {
                                handleBananaColorChange(null);
                            } else {
                                handleBananaColorChange('red');
                            }
                        };

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center relative`}
                                style={{ minWidth: '160px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <div className="flex items-center justify-center">
                                    <div className="relative flex items-center justify-center gap-0.5">
                                        <button
                                            type="button"
                                            onClick={handleUrgencyClick}
                                            disabled={!isUrgencyToggleable}
                                            className={`p-1.5 rounded-md border transition-all ${bananaChipClass} ${bananaHoverClass} ${!isUrgencyToggleable ? 'opacity-90 cursor-default' : 'cursor-pointer'}`}
                                            title={isHold ? 'Hold – always urgent (red)' : (effectiveColor === 'red' ? 'Marked urgent – click for normal' : 'Click to mark urgent (red)')}
                                        >
                                            <span className="inline-flex items-center gap-0.5">
                                                {Array.from({ length: bananaCount }, (_, i) => (
                                                    <BananaIcon key={i} color={effectiveColor} size={bananaCount === 1 ? 22 : 18} />
                                                ))}
                                            </span>
                                        </button>
                                    </div>
                                </div>
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

                        const solidStyle = {
                            backgroundColor: currentStageColors.light,
                            color: currentStageColors.text,
                            borderColor: currentStageColors.border
                        };

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center relative`}
                                style={{ minWidth: '160px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <div className="flex items-center justify-center">
                                    <div className="relative flex-1 min-w-0 max-w-full">
                                        <button
                                            type="button"
                                            onClick={() => !updatingStage && setShowStageDropdown((v) => !v)}
                                            disabled={updatingStage}
                                            className={`w-full min-w-[100px] px-2 py-0.5 text-[10px] border-2 rounded font-medium text-center transition-all ${updatingStage ? 'opacity-50 cursor-wait' : ''}`}
                                            style={solidStyle}
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
                                                <div className="absolute left-0 right-0 top-full mt-0.5 rounded-md border-2 border-gray-300 dark:border-slate-500 shadow-lg z-20 min-w-[100px] max-h-64 overflow-y-auto overflow-x-hidden bg-white dark:bg-slate-800 flex flex-col">
                                                    {(stageToGroup
                                                        ? [...stageOptions].sort((a, b) => {
                                                            const groupOrder = { FABRICATION: 0, READY_TO_SHIP: 1, COMPLETE: 2 };
                                                            const ga = stageToGroup[a.value] ?? 'FABRICATION';
                                                            const gb = stageToGroup[b.value] ?? 'FABRICATION';
                                                            return (groupOrder[ga] ?? 0) - (groupOrder[gb] ?? 0);
                                                          })
                                                        : stageOptions
                                                    ).map((option) => {
                                                        const optionColors = getStageColors(option.value);
                                                        const isSelected = option.value === localStage;
                                                        return (
                                                            <button
                                                                key={option.value}
                                                                type="button"
                                                                onClick={() => {
                                                                    handleStageChange(option.value);
                                                                    setShowStageDropdown(false);
                                                                }}
                                                                className={`w-full px-2 py-1.5 text-[10px] font-medium text-center first:rounded-t-md last:rounded-b-md hover:brightness-95 ${isSelected ? 'ring-1 ring-inset ring-gray-400 dark:ring-slate-400' : ''}`}
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
                                </div>
                            </td>
                        );
                    }

                    // Handle Fab Order column with editable input
                    if (column === 'Fab Order') {
                        const displayValue = localFabOrder === null || localFabOrder === undefined ? '—' : formatCellValue(localFabOrder, column);
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center`}
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
                                                setFabOrderInputValue(localFabOrder === null || localFabOrder === undefined ? '' : String(localFabOrder));
                                            }
                                        }
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                            e.target.blur();
                                        } else if (e.key === 'Escape') {
                                            setFabOrderInputValue(localFabOrder === null || localFabOrder === undefined ? '' : String(localFabOrder));
                                            e.target.blur();
                                        }
                                    }}
                                    disabled={updatingFabOrder}
                                    className={`w-full px-1 py-0.5 text-[10px] border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 text-center ${updatingFabOrder ? 'opacity-50 cursor-wait' : ''}`}
                                    placeholder="—"
                                    style={{ minWidth: '60px' }}
                                />
                            </td>
                        );
                    }

                    // Handle Notes column with editable textarea
                    if (column === 'Notes') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} py-0.5 text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center whitespace-normal`}
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
                                        }
                                    }}
                                    disabled={updatingNotes}
                                    className={`w-full px-1 py-0.5 text-[10px] border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 resize-none ${updatingNotes ? 'opacity-50 cursor-wait' : ''}`}
                                    placeholder="—"
                                    rows={2}
                                    style={{ minWidth: '120px' }}
                                />
                            </td>
                        );
                    }

                    // Handle Job Comp column - editable text input
                    if (column === 'Job Comp') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                data-editable-x="true"
                                className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center`}
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
                                    className={`w-full px-1 py-0.5 text-[10px] border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 text-center ${updatingJobComp ? 'opacity-50 cursor-wait' : ''}`}
                                    placeholder="—"
                                    style={{ minWidth: '48px' }}
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
                                className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center`}
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
                                    className={`w-full px-1 py-0.5 text-[10px] border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 text-center ${updatingInvoiced ? 'opacity-50 cursor-wait' : ''}`}
                                    placeholder="—"
                                    style={{ minWidth: '48px' }}
                                />
                            </td>
                        );
                    }

                    // Handle Start install column with clickable cell that opens modal
                    if (column === 'Start install') {
                        const displayValue = formatDate(localStartInstall);
                        // Hard date is when start_install_formulaTF is explicitly false and there's a date value
                        const isHardDate = row['start_install_formulaTF'] === false && localStartInstall;
                        // Formula date is when start_install_formulaTF is true or formula starts with '='
                        const isFormulaDate = row['start_install_formulaTF'] === true || (row['start_install_formula'] && row['start_install_formula'].startsWith('='));
                        // IMPORTANT: avoid conflicting bg-* utilities (Tailwind utility order, not class string order,
                        // determines the winner). If we include both rowBgClass and bg-red-500, the row bg can win,
                        // leaving white text on a light background (looks blank until hover).
                        const startInstallBgClass = isHardDate ? 'bg-red-500 text-white hover:bg-red-600 font-semibold' : `${rowBgClass} text-gray-900 dark:text-slate-100 hover:bg-accent-50 dark:hover:bg-slate-600`;

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${startInstallBgClass} border-r border-gray-300 dark:border-slate-600 text-center cursor-pointer transition-colors ${updatingStartInstall ? 'opacity-50' : ''}`}
                                onClick={() => !updatingStartInstall && setIsStartInstallModalOpen(true)}
                                title={isFormulaDate ? `${displayValue} (Formula-driven - Click to set hard date)` : `${displayValue} - Click to edit`}
                            >
                                <div className="flex items-center justify-center gap-1">
                                    <span>{displayValue}</span>
                                    {isFormulaDate && (
                                        <span className="text-[8px] text-gray-500 dark:text-slate-400" title="Formula-driven date">
                                            📐
                                        </span>
                                    )}
                                </div>
                            </td>
                        );
                    }

                    // For Job and Description, show full value in tooltip
                    const tooltipValue = shouldWrapAndTruncate ? rawValue : rawValue;

                    // Handle Job column - make it clickable to open modal
                    if (column === 'Job') {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} py-0.5 text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center cursor-pointer hover:bg-accent-50 dark:hover:bg-slate-600 transition-colors`}
                                title={`${tooltipValue} - Click to view details`}
                                onClick={() => setIsModalOpen(true)}
                                style={{
                                    maxWidth: '120px',
                                    width: '120px'
                                }}
                            >
                                <div
                                    style={{
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        lineHeight: '1.2',
                                        textAlign: 'center'
                                    }}
                                >
                                    <span className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline">
                                        {rawValue}
                                    </span>
                                </div>
                            </td>
                        );
                    }

                    // Handle Release # column - make it a link to viewer_url if available
                    if (column === 'Release #') {
                        const viewerUrl = row.viewer_url;
                        // Check if viewer_url exists and is not empty
                        if (viewerUrl && viewerUrl.trim() !== '') {
                            return (
                                <td
                                    key={`${row.id}-${column}`}
                                    className={`${paddingClass} py-0.5 text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center`}
                                    title={`${rawValue} - Click to open Procore viewer`}
                                >
                                    <a
                                        href={viewerUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline cursor-pointer"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        {rawValue}
                                    </a>
                                </td>
                            );
                        }
                        // If no viewer_url, render normally
                    }

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`${paddingClass} py-0.5 text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-gray-900 dark:text-slate-100 text-center ${shouldWrapAndTruncate
                                ? ''
                                : whitespaceClass
                                }`}
                            title={tooltipValue}
                            style={shouldWrapAndTruncate ? {
                                maxWidth: column === 'Job' ? '120px' : '150px',
                                width: column === 'Job' ? '120px' : '150px'
                            } : {}}
                        >
                            {shouldWrapAndTruncate ? (
                                <div
                                    style={{
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        lineHeight: '1.2',
                                        textAlign: 'center'
                                    }}
                                >
                                    {rawValue}
                                </div>
                            ) : (
                                rawValue
                            )}
                        </td>
                    );
                })}
                {isAdmin && (
                    <td
                        className="px-2 py-0.5 text-center align-middle border-r border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 w-12 relative"
                        style={{ width: '48px' }}
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
                                    <li
                                        onClick={() => handleEditColumn('job_name')}
                                        className="px-4 py-2 text-sm text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-600 cursor-pointer whitespace-nowrap"
                                    >
                                        Edit column…
                                    </li>
                                    <li
                                        onClick={handleDeleteRow}
                                        className="px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-slate-600 cursor-pointer whitespace-nowrap"
                                    >
                                        Delete row
                                    </li>
                                </ul>
                            </>
                        )}
                    </td>
                )}
            </tr>
            <JobDetailsModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                job={row}
            />
            <StartInstallDateModal
                isOpen={isStartInstallModalOpen}
                onClose={() => setIsStartInstallModalOpen(false)}
                currentDate={localStartInstall}
                onSave={handleStartInstallSave}
                jobNumber={row['Job #']}
                releaseNumber={row['Release #']}
                startInstallFormulaTF={row['start_install_formulaTF']}
            />
            {showEditModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-lg p-6 max-w-md w-full mx-4">
                        <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 mb-4">Edit Column</h2>
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                                Column
                            </label>
                            <select
                                value={editField}
                                onChange={(e) => {
                                    const field = e.target.value;
                                    setEditField(field);
                                    const col = EDITABLE_COLUMNS.find(c => c.field === field);
                                    if (col) {
                                        const currentValue = row[col.label] || '';
                                        setEditValue(currentValue);
                                    }
                                }}
                                className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                            >
                                <option value="">Select a column...</option>
                                {EDITABLE_COLUMNS.map((col) => (
                                    <option key={col.field} value={col.field}>
                                        {col.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                        {editField && (
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                                    Value
                                </label>
                                {EDITABLE_COLUMNS.find(c => c.field === editField)?.type === 'date' ? (
                                    <input
                                        type="date"
                                        value={editValue}
                                        onChange={(e) => setEditValue(e.target.value)}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                                    />
                                ) : EDITABLE_COLUMNS.find(c => c.field === editField)?.type === 'number' ? (
                                    <input
                                        type="number"
                                        step="0.01"
                                        value={editValue}
                                        onChange={(e) => setEditValue(e.target.value)}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                                    />
                                ) : (
                                    <input
                                        type="text"
                                        value={editValue}
                                        onChange={(e) => setEditValue(e.target.value)}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100"
                                    />
                                )}
                            </div>
                        )}
                        <div className="flex gap-2">
                            <button
                                onClick={handleSaveEdit}
                                disabled={saving || !editField}
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

