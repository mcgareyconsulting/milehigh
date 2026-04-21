/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Renders a single submittal table row on the Drafting Work Load page with inline editing for order, notes, status, and due date.
 * exports:
 *   TableRow: Submittal table row with drag-drop reordering and role-gated inline editing
 * imports_from: [react, ../utils/formatters, ../constants/jumpToHighlight]
 * imported_by: [frontend/src/pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - Notes and drafting status are editable by any authenticated user
 *   - Due date editing is gated by canEditDrafterFields (admin or drafter)
 *   - Order number editing is admin-only and restricted to single-assignee rows
 *   - Bump/step-order actions reorder relative to allRows for correct position calculation
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React, { useState, useEffect, useRef } from 'react';
import { formatDate, formatDateShort } from '../utils/formatters';
import { JUMP_TO_HIGHLIGHT_CLASS } from '../constants/jumpToHighlight';
import MentionInput from './shared/MentionInput';

export function TableRow({ row, columns, formatCellValue, formatDate, onOrderNumberChange, onNotesChange, onStatusChange, onProcoreStatusChange, procoreStatusOptions, selectedTab, onBump, onDueDateChange, onStepOrder, allRows, rowIndex, isAdmin = false, isDrafter = false, isJumpToHighlight, onDragStart, onDragOver, onDragLeave, onDragEnd, onDrop, isDragOver, dragOverHalf, mentionableUsers = [] }) {
    const [editingOrderNumber, setEditingOrderNumber] = useState(false);
    const [orderNumberValue, setOrderNumberValue] = useState('');
    const [editingNotes, setEditingNotes] = useState(false);
    const [notesValue, setNotesValue] = useState('');
    const [pendingNotes, setPendingNotes] = useState(null);
    const [editingDueDate, setEditingDueDate] = useState(false);
    const [dueDateValue, setDueDateValue] = useState('');
    const inputRef = useRef(null);
    const notesInputRef = useRef(null);
    const dueDateInputRef = useRef(null);

    const canEditDrafterFields = isAdmin || isDrafter;

    const submittalId = row['Submittals Id'] || row.submittal_id;
    const ballInCourt = row.ball_in_court ?? row['BIC'] ?? '';
    const hasMultipleAssignees = String(ballInCourt).includes(',');

    const formatTypeValue = (value) => {
        if (value === null || value === undefined || value === '') {
            return value;
        }
        const typeMap = {
            'Submittal For Gc  Approval': 'Sub GC',
            'Submittal for GC  Approval': 'Sub GC',
            'Drafting Release Review': 'DRR',
        };
        return typeMap[value] || value;
    };

    const handleOrderNumberFocus = () => {
        // Only allow editing if user is admin
        if (!isAdmin) {
            return;
        }

        // Check if this row has multiple assignees (comma-separated ball_in_court)
        const ballInCourt = row.ball_in_court ?? row['BIC'] ?? '';
        const hasMultipleAssignees = String(ballInCourt).includes(',');

        // Don't allow editing order number for multiple assignees (reviewers)
        if (hasMultipleAssignees) {
            return;
        }

        const currentValue = row['ORDER #'] ?? row.order_number ?? '';
        setOrderNumberValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
        setEditingOrderNumber(true);
    };

    const handleOrderNumberBlur = () => {
        setEditingOrderNumber(false);
        if (submittalId && onOrderNumberChange) {
            onOrderNumberChange(submittalId, orderNumberValue);
        }
    };

    const handleOrderNumberKeyDown = (e) => {
        if (e.key === 'Enter') {
            e.target.blur();
        } else if (e.key === 'Escape') {
            const currentValue = row['ORDER #'] ?? row.order_number ?? '';
            setOrderNumberValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
            setEditingOrderNumber(false);
        }
    };

    const handleNotesFocus = () => {
        const currentValue = row['NOTES'] ?? row.notes ?? '';
        setNotesValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
        setEditingNotes(true);
    };

    const handleNotesBlur = () => {
        setEditingNotes(false);
        setPendingNotes(notesValue);
        if (submittalId && onNotesChange) {
            onNotesChange(submittalId, notesValue);
        }
    };

    const rowNotes = row['NOTES'] ?? row.notes ?? '';
    useEffect(() => {
        if (pendingNotes === null) return;
        if (String(rowNotes) === String(pendingNotes)) {
            setPendingNotes(null);
        }
    }, [rowNotes, pendingNotes]);

    useEffect(() => {
        if (editingOrderNumber && inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
        }
    }, [editingOrderNumber]);

    useEffect(() => {
        if (editingNotes && notesInputRef.current) {
            notesInputRef.current.focus();
            notesInputRef.current.select();
        }
    }, [editingNotes]);

    useEffect(() => {
        if (editingDueDate && dueDateInputRef.current) {
            dueDateInputRef.current.focus();
            dueDateInputRef.current.select();
        }
    }, [editingDueDate]);

    const handleDueDateFocus = () => {
        // Only allow editing if user is admin or drafter
        if (!canEditDrafterFields) {
            return;
        }
        const currentValue = row['DUE DATE'] ?? row.due_date ?? '';
        // Format date for input (YYYY-MM-DD)
        let formattedDate = '';
        if (currentValue) {
            // If it's already in YYYY-MM-DD format, use it directly
            if (typeof currentValue === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(currentValue)) {
                formattedDate = currentValue;
            } else {
                // Try to extract YYYY-MM-DD from ISO string or Date object
                try {
                    const dateStr = typeof currentValue === 'string' ? currentValue.split('T')[0] : currentValue;
                    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
                        formattedDate = dateStr;
                    } else {
                        // Fallback: parse as Date and format
                        const date = new Date(currentValue);
                        if (!isNaN(date.getTime())) {
                            // Use UTC methods to avoid timezone shift
                            const year = date.getUTCFullYear();
                            const month = String(date.getUTCMonth() + 1).padStart(2, '0');
                            const day = String(date.getUTCDate()).padStart(2, '0');
                            formattedDate = `${year}-${month}-${day}`;
                        }
                    }
                } catch (e) {
                    // Invalid date, leave empty
                }
            }
        }
        setDueDateValue(formattedDate);
        setEditingDueDate(true);
    };

    const handleDueDateBlur = () => {
        setEditingDueDate(false);
        if (submittalId && onDueDateChange) {
            // Send empty string if cleared, otherwise send the date value
            const valueToSend = dueDateValue.trim() === '' ? null : dueDateValue;
            onDueDateChange(submittalId, valueToSend);
        }
    };

    const handleDueDateKeyDown = (e) => {
        if (e.key === 'Enter') {
            e.target.blur();
        } else if (e.key === 'Escape') {
            const currentValue = row['DUE DATE'] ?? row.due_date ?? '';
            let formattedDate = '';
            if (currentValue) {
                // If it's already in YYYY-MM-DD format, use it directly
                if (typeof currentValue === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(currentValue)) {
                    formattedDate = currentValue;
                } else {
                    // Try to extract YYYY-MM-DD from ISO string
                    try {
                        const dateStr = typeof currentValue === 'string' ? currentValue.split('T')[0] : currentValue;
                        if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
                            formattedDate = dateStr;
                        } else {
                            // Fallback: parse as Date and format
                            const date = new Date(currentValue);
                            if (!isNaN(date.getTime())) {
                                // Use UTC methods to avoid timezone shift
                                const year = date.getUTCFullYear();
                                const month = String(date.getUTCMonth() + 1).padStart(2, '0');
                                const day = String(date.getUTCDate()).padStart(2, '0');
                                formattedDate = `${year}-${month}-${day}`;
                            }
                        }
                    } catch (e) {
                        // Invalid date, leave empty
                    }
                }
            }
            setDueDateValue(formattedDate);
            setEditingDueDate(false);
        }
    };

    const rowType = row.type ?? row['TYPE'] ?? '';
    const isDraftingReleaseReview = rowType === 'Drafting Release Review';
    
    // Check if status is HOLD for yellow background
    const currentStatus = row.submittal_drafting_status ?? row['COMP. STATUS'] ?? '';
    const isHoldStatus = currentStatus === 'HOLD';

    // Alternate row background colors, but override with yellow if status is HOLD
    const baseRowBgClass = rowIndex % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-gray-200 dark:bg-slate-700';
    const rowBgClass = isHoldStatus ? 'bg-yellow-200 dark:bg-yellow-900/40' : baseRowBgClass;

    // Prevent drag start from protected cells
    const handleProtectedCellMouseDown = (e) => {
        // Allow select elements to work normally (don't prevent default)
        const target = e.target;
        const isSelectElement = target.tagName === 'SELECT' ||
            target.closest('select') !== null;

        if (isSelectElement) {
            // Don't prevent default for select elements - let them open normally
            e.stopPropagation();
            return;
        }

        e.stopPropagation();
        // Prevent drag from starting on these cells
        e.preventDefault();
    };

    return (
        <>
            <tr
                className={`${rowBgClass} hover:bg-gray-100 dark:hover:bg-slate-600 transition-all duration-200 border-b border-gray-300 dark:border-slate-600 ${isJumpToHighlight ? JUMP_TO_HIGHLIGHT_CLASS : ''} ${
                    isDragOver && dragOverHalf === 'top' ? 'border-t-2 border-t-blue-400 dark:border-t-blue-300 bg-blue-50 dark:bg-blue-900/30' : ''
                } ${isDragOver && dragOverHalf === 'bottom' ? 'border-b-2 border-b-blue-400 dark:border-b-blue-300 bg-blue-50 dark:bg-blue-900/30' : ''}`}
                data-submittal-id={submittalId}
                onDragStart={(e) => {
                    // Only allow drag from title cell
                    const isTitle = e.target.closest('td')?.classList.contains('dwl-col-title');
                    if (isTitle && onDragStart) {
                        onDragStart(e, row);
                    } else {
                        e.preventDefault();
                    }
                }}
                onDragOver={(e) => {
                    if (onDragOver) {
                        onDragOver(e, row);
                    }
                }}
                onDragLeave={(e) => {
                    if (onDragLeave) {
                        onDragLeave(e);
                    }
                }}
                onDragEnd={(e) => {
                    if (onDragEnd) {
                        onDragEnd(e);
                    }
                }}
                onDrop={(e) => {
                    if (onDrop) {
                        onDrop(e, row, allRows);
                    }
                }}
            >
                {columns.map((column) => {
                    const isOrderNumber = column === 'ORDER #';
                    const isSubmittalId = column === 'Submittals Id';
                    const isType = column === 'TYPE';
                    const isNotes = column === 'NOTES';
                    const isProcoreStatus = column === 'PROCORE STATUS';
                    const isStatus = column === 'COMP. STATUS';
                    const isProjectName = column === 'NAME';
                    const isBallInCourt = column === 'BIC';
                    const isLastBIC = column === 'LAST BIC';
                    const isLifespan = column === 'LIFESPAN';
                    const isDueDate = column === 'DUE DATE';

                    // Skip rendering the Submittals Id column
                    if (isSubmittalId) {
                        return null;
                    }

                    // Custom width for columns (matching header widths - perfect for laptop screens)
                    // CSS media queries handle larger screens
                    let customWidthClass = '';
                    let customStyle = {};
                    let columnClass = '';
                    if (isSubmittalId) {
                        customWidthClass = 'w-32'; // Accommodate 8-10 digit ID + operations link icon
                        columnClass = 'dwl-col-submittal-id';
                    } else if (column === 'PROJ. #') {
                        customWidthClass = 'w-20'; // Accommodate 3-4 digit number
                        columnClass = 'dwl-col-project-number';
                    } else if (column === 'TITLE') {
                        customStyle = { maxWidth: '280px' };
                        columnClass = 'dwl-col-title';
                    } else if (column === 'TYPE') {
                        customStyle = { maxWidth: '80px' };
                        columnClass = 'dwl-col-type';
                    } else if (column === 'SUB MANAGER') {
                        customWidthClass = 'w-32';
                        columnClass = 'dwl-col-sub-manager';
                    } else if (isOrderNumber) {
                        columnClass = 'dwl-col-order-number';
                    } else if (isNotes) {
                        columnClass = 'dwl-col-notes';
                    } else if (isProcoreStatus) {
                        columnClass = 'dwl-col-procore-status';
                    } else if (isStatus) {
                        columnClass = 'dwl-col-comp-status';
                    } else if (isProjectName) {
                        columnClass = 'dwl-col-name';
                    } else if (isBallInCourt) {
                        columnClass = 'dwl-col-bic';
                    } else if (isLastBIC) {
                        customStyle = { maxWidth: '100px' };
                        columnClass = 'dwl-col-last-bic-update';
                    } else if (isLifespan) {
                        customStyle = { maxWidth: '75px' };
                        columnClass = 'dwl-col-lifespan';
                    } else if (isDueDate) {
                        customStyle = { maxWidth: '120px' };
                        columnClass = 'dwl-col-due-date';
                    }

                    // Apply Type truncation mapping before formatting
                    let rawValue = row[column];
                    if (isType) {
                        rawValue = formatTypeValue(rawValue);
                    }
                    let cellValue = formatCellValue(rawValue);

                    if (isOrderNumber && editingOrderNumber) {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center dwl-col-order-number`}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <input
                                    ref={inputRef}
                                    type="text"
                                    value={orderNumberValue}
                                    onChange={(e) => setOrderNumberValue(e.target.value)}
                                    onBlur={handleOrderNumberBlur}
                                    onKeyDown={handleOrderNumberKeyDown}
                                    className="w-full px-0.5 py-0 text-xs border-2 border-accent-500 rounded-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white dark:bg-slate-700 font-medium text-gray-900 dark:text-slate-100"
                                    style={{ minWidth: '30px', maxWidth: '50px' }}
                                />
                            </td>
                        );
                    }

                    if (isOrderNumber) {
                        // isEditable requires admin and no multiple assignees
                        const isEditable = isAdmin && !hasMultipleAssignees;

                        // Display Order Number - show all values (including decimals and numbers > 10)
                        const rawOrderValue = row['ORDER #'] ?? row.order_number;
                        let displayOrder = '';

                        if (rawOrderValue !== null && rawOrderValue !== undefined && rawOrderValue !== '') {
                            const numericOrder = typeof rawOrderValue === 'number'
                                ? rawOrderValue
                                : parseFloat(rawOrderValue);

                            if (!Number.isNaN(numericOrder)) {
                                displayOrder = String(numericOrder);
                            }
                        }

                        // Check bump eligibility:
                        // - Ordered (integer >= 1) → bumps to urgency slot
                        // - Unordered (null) → appended to end of ordered list
                        const rawIsNull = rawOrderValue === null || rawOrderValue === undefined || rawOrderValue === '';
                        const rawIsIntegerOrdered = !rawIsNull &&
                            typeof rawOrderValue === 'number' &&
                            rawOrderValue >= 1 &&
                            rawOrderValue === Math.floor(rawOrderValue);
                        const canBump = isAdmin && (rawIsNull || rawIsIntegerOrdered) && ballInCourt && !hasMultipleAssignees;

                        const handleBumpClick = (e) => {
                            e.stopPropagation();
                            if (submittalId && onBump && canBump) {
                                onBump(submittalId);
                            }
                        };

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 dark:border-slate-600 text-center dwl-col-order-number`}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <div className="flex items-center justify-center gap-1">
                                    <div 
                                        className={`px-0.5 py-0 text-xs border rounded-sm font-medium min-w-[20px] max-w-[50px] inline-block transition-colors ${isEditable
                                            ? 'border-gray-300 dark:border-slate-500 bg-gray-50 dark:bg-slate-600 hover:bg-white dark:hover:bg-slate-500 hover:border-accent-400 cursor-text text-gray-700 dark:text-slate-200'
                                            : 'border-gray-200 dark:border-slate-600 bg-gray-100 dark:bg-slate-700 cursor-not-allowed text-gray-500 dark:text-slate-400 opacity-75'
                                            }`}
                                        onClick={isEditable ? handleOrderNumberFocus : undefined}
                                        title={isEditable ? "Click to edit order number" : "Order number editing disabled for multiple assignees (reviewers)"}
                                    >
                                        {displayOrder}
                                    </div>
                                    {canBump && onBump && (
                                        <button
                                            onClick={handleBumpClick}
                                            className="px-1.5 py-0.5 text-xs font-medium bg-accent-500 hover:bg-accent-600 text-white rounded transition-colors shadow-sm"
                                            title={rawIsNull ? "Bump: add to end of ordered list" : "Bump submittal to 0.9 urgency slot"}
                                        >
                                            Bump
                                        </button>
                                    )}
                                </div>
                            </td>
                        );
                    }

                    if (isNotes && editingNotes) {
                        const handleCancelNotes = () => {
                            const currentValue = row['NOTES'] ?? row.notes ?? '';
                            setNotesValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
                            setEditingNotes(false);
                        };
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dark:border-slate-600 dwl-col-notes`}
                                style={{ maxWidth: '350px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <MentionInput
                                    ref={notesInputRef}
                                    value={notesValue}
                                    onChange={setNotesValue}
                                    onBlur={handleNotesBlur}
                                    onCancel={handleCancelNotes}
                                    users={mentionableUsers}
                                    multiline
                                    rows={1}
                                    placeholder="Add notes... (type @ to mention)"
                                    className="w-full px-1 py-0.5 text-xs border-2 border-accent-500 rounded-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 resize-none shadow-sm transition-all text-center"
                                />
                            </td>
                        );
                    }

                    if (isNotes) {
                        if (pendingNotes !== null) {
                            cellValue = pendingNotes === '' ? '—' : pendingNotes;
                        }
                        const hasNotes = cellValue && cellValue !== '—';
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dark:border-slate-600 dwl-col-notes`}
                                style={{ maxWidth: '350px' }}
                                draggable={false}
                                onClick={handleNotesFocus}
                                onMouseDown={handleProtectedCellMouseDown}
                                title="Click to edit notes"
                            >
                                <div className={`px-0.5 py-0 text-xs rounded-sm border transition-all min-h-[10px] text-center ${
                                    hasNotes
                                        ? 'border-gray-200 dark:border-slate-500 bg-gray-50 dark:bg-slate-600 hover:bg-white dark:hover:bg-slate-500 hover:border-accent-300 text-gray-800 dark:text-slate-200 cursor-text'
                                        : 'border-gray-200 dark:border-slate-500 bg-gray-50/50 dark:bg-slate-600/50 hover:bg-gray-100 dark:hover:bg-slate-500 hover:border-accent-300 text-gray-500 dark:text-slate-400 cursor-text'
                                    }`}>
                                    {hasNotes ? (
                                        <div className="whitespace-normal break-words leading-tight">
                                            {cellValue}
                                        </div>
                                    ) : (
                                        <span className="italic">Click to add notes...</span>
                                    )}
                                </div>
                            </td>
                        );
                    }


                    if (isProcoreStatus) {
                        // Procore Status column: current submittal status from Procore (default value) + dropdown to patch
                        const currentProcoreStatus = row.status ?? row['PROCORE STATUS'] ?? '';
                        const hasOptions = Array.isArray(procoreStatusOptions) && procoreStatusOptions.length > 0;
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dark:border-slate-600 dwl-col-procore-status`}
                                style={{ maxWidth: '96px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                {hasOptions && isAdmin ? (
                                    <select
                                        value={procoreStatusOptions.find((o) => o.name === currentProcoreStatus)?.id ?? ''}
                                        onChange={(e) => {
                                            const val = e.target.value;
                                            if (submittalId && onProcoreStatusChange && val !== '') {
                                                const statusId = Number(val);
                                                if (!Number.isNaN(statusId)) onProcoreStatusChange(submittalId, statusId);
                                            }
                                        }}
                                        className="w-full px-0.5 py-0.5 text-xs border border-gray-300 dark:border-slate-500 rounded text-center bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 cursor-pointer"
                                        title="Select Procore status (updates submittal in Procore)"
                                    >
                                        <option value="">—</option>
                                        {procoreStatusOptions.map((opt) => (
                                            <option key={opt.id} value={opt.id}>
                                                {opt.name}
                                            </option>
                                        ))}
                                    </select>
                                ) : (
                                    <span className="text-xs text-gray-700 dark:text-slate-200">{currentProcoreStatus || '—'}</span>
                                )}
                            </td>
                        );
                    }

                    if (isStatus) {
                        // Status column: always HOLD / NEED VIF / STARTED drafting dropdown
                        const currentStatus = row.submittal_drafting_status ?? row['COMP. STATUS'] ?? '';
                        const statusOptions = ['STARTED', 'NEED VIF', 'HOLD'];

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dark:border-slate-600 dwl-col-status`}
                                style={{ maxWidth: '96px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <select
                                    value={currentStatus || ''}
                                    onChange={(e) => {
                                        if (submittalId && onStatusChange) {
                                            onStatusChange(submittalId, e.target.value);
                                        }
                                    }}
                                    className="w-full px-0.5 py-0.5 text-xs border border-gray-300 dark:border-slate-500 rounded text-center bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 cursor-pointer"
                                    title="Select drafting status (HOLD / NEED VIF / STARTED)"
                                >
                                    <option value="">—</option>
                                    {statusOptions.map((option) => (
                                        <option key={option} value={option}>
                                            {option}
                                        </option>
                                    ))}
                                </select>
                            </td>
                        );
                    }

                    if (isDueDate && editingDueDate) {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dark:border-slate-600 dwl-col-due-date`}
                                style={{ maxWidth: '120px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <input
                                    ref={dueDateInputRef}
                                    type="date"
                                    value={dueDateValue}
                                    onChange={(e) => setDueDateValue(e.target.value)}
                                    onBlur={handleDueDateBlur}
                                    onKeyDown={handleDueDateKeyDown}
                                    className="w-full px-0.5 py-0 text-xs border-2 border-accent-500 rounded-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white dark:bg-slate-700 font-medium text-gray-900 dark:text-slate-100"
                                />
                            </td>
                        );
                    }

                    if (isDueDate) {
                        const dueDateValue = row['DUE DATE'] ?? row.due_date ?? '';
                        const hasDueDate = dueDateValue && dueDateValue !== '';
                        // Use formatDateShort which now handles date-only strings without timezone conversion
                        const formattedDate = hasDueDate ? formatDateShort(dueDateValue) : '';

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dark:border-slate-600 dwl-col-due-date`}
                                style={{ maxWidth: '120px' }}
                                draggable={false}
                                onClick={canEditDrafterFields ? handleDueDateFocus : undefined}
                                onMouseDown={handleProtectedCellMouseDown}
                                title={canEditDrafterFields ? "Click to edit due date" : "Read-only"}
                            >
                                <div className={`px-0.5 py-0 text-xs rounded-sm border transition-all min-h-[10px] text-center ${
                                    canEditDrafterFields
                                        ? hasDueDate
                                            ? 'border-red-300 dark:border-red-700 bg-red-100 dark:bg-red-900/40 hover:bg-red-200 dark:hover:bg-red-800/50 hover:border-red-400 text-red-900 dark:text-red-200 font-medium cursor-text'
                                            : 'border-gray-200 dark:border-slate-500 bg-gray-50/50 dark:bg-slate-600/50 hover:bg-gray-100 dark:hover:bg-slate-500 hover:border-accent-300 text-gray-500 dark:text-slate-400 cursor-text'
                                        : hasDueDate
                                            ? 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 font-medium cursor-default'
                                            : 'border-gray-200 dark:border-slate-600 bg-gray-50/50 dark:bg-slate-700/50 text-gray-400 dark:text-slate-500 cursor-default'
                                }`}>
                                    {hasDueDate ? formattedDate : <span className="italic">{canEditDrafterFields ? "Click to add..." : "—"}</span>}
                                </div>
                            </td>
                        );
                    }

                    // Apply light green background for Type cell when type is "Drafting Release Review"
                    const cellBgClass = isType && isDraftingReleaseReview
                        ? 'bg-green-100 dark:bg-green-900/40'
                        : rowBgClass;

                    // Handle NAME (project name) truncation to 20 characters
                    if (isProjectName) {
                        const fullProjectName = cellValue;
                        const truncatedProjectName = fullProjectName && fullProjectName.length > 20
                            ? fullProjectName.substring(0, 20) + '...'
                            : fullProjectName;

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-1 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 dark:border-slate-600 text-gray-900 dark:text-slate-100 text-center dwl-col-name`}
                                style={{ maxWidth: '280px' }}
                                title={fullProjectName}
                            >
                                {truncatedProjectName}
                            </td>
                        );
                    }

                    // Handle Ball In Court: wrap if value is longer than 'Rourke Alvarado' (15 chars)
                    if (isBallInCourt) {
                        // Get the value directly from row to ensure we have it
                        const ballInCourtValue = row.ball_in_court ?? row['BIC'] ?? rawValue ?? '';
                        const ballInCourtString = String(ballInCourtValue);
                        const shouldWrap = ballInCourtString.length > 15; // 'Rourke Alvarado' is 15 chars
                        const whitespaceClass = shouldWrap ? 'whitespace-normal break-words' : 'whitespace-nowrap';

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-1 py-0.5 ${whitespaceClass} text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 dark:border-slate-600 text-gray-900 dark:text-slate-100 text-center dwl-col-bic`}
                                style={{ maxWidth: '180px' }}
                                title={cellValue}
                            >
                                {cellValue}
                            </td>
                        );
                    }

                    // Handle Last BIC column - show days since last ball in court update
                    if (isLastBIC) {
                        const daysSinceUpdate = row['LAST BIC'] ?? row.days_since_ball_in_court_update;
                        const displayValue = daysSinceUpdate !== null && daysSinceUpdate !== undefined
                            ? `${daysSinceUpdate} days`
                            : '—';

                        // Determine background color based on days
                        let bgColorClass = '';
                        if (daysSinceUpdate !== null && daysSinceUpdate !== undefined) {
                            if (daysSinceUpdate >= 5) {
                                bgColorClass = 'bg-red-200 dark:bg-red-900/50 text-red-900 dark:text-red-200'; // Red for 5+ days
                            } else if (daysSinceUpdate >= 3) {
                                bgColorClass = 'bg-yellow-200 dark:bg-yellow-900/40 text-yellow-900 dark:text-yellow-200'; // Yellow for 3-4 days
                            }
                        }

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-1 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${bgColorClass || cellBgClass} ${!bgColorClass ? 'text-gray-900 dark:text-slate-100' : ''} border-r border-gray-300 dark:border-slate-600 text-center dwl-col-last-bic`}
                                style={{ maxWidth: '100px' }}
                                title={daysSinceUpdate !== null && daysSinceUpdate !== undefined ? `${daysSinceUpdate} days` : 'No ball in court update recorded'}
                            >
                                {displayValue}
                            </td>
                        );
                    }

                    // Handle LIFESPAN column - days since creation (how old the submittal is)
                    if (isLifespan) {
                        const lifespanValue = row['LIFESPAN'] ?? row.lifespan;
                        const displayLifespan = lifespanValue !== null && lifespanValue !== undefined
                            ? `${lifespanValue} days`
                            : '—';

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 dark:border-slate-600 text-gray-900 dark:text-slate-100 text-center dwl-col-lifespan`}
                                style={{ maxWidth: '75px' }}
                                title={lifespanValue !== null && lifespanValue !== undefined ? `${lifespanValue} days since creation` : 'N/A'}
                            >
                                {displayLifespan}
                            </td>
                        );
                    }

                    // Handle TITLE column - plain text display with optional up/down step arrows + drag handle
                    if (column === 'TITLE') {
                        const rawOrderVal = row['ORDER #'] ?? row.order_number;
                        const numericOrder = rawOrderVal !== null && rawOrderVal !== undefined
                            ? parseFloat(rawOrderVal) : null;
                        const isOrdered = numericOrder !== null && !isNaN(numericOrder) && numericOrder >= 1;
                        const isUrgent = numericOrder !== null && !isNaN(numericOrder) && numericOrder > 0 && numericOrder < 1;
                        const canStep = isAdmin && !hasMultipleAssignees && ballInCourt && (isOrdered || isUrgent);

                        let canStepUp = false;
                        let canStepDown = false;

                        if (canStep && allRows) {
                            const sameGroupOrders = allRows
                                .filter(r => String(r.ball_in_court ?? r['BIC'] ?? '') === String(ballInCourt))
                                .map(r => parseFloat(r['ORDER #'] ?? r.order_number ?? 'x'))
                                .filter(o => !isNaN(o));

                            const zoneOrders = isUrgent
                                ? sameGroupOrders.filter(o => o > 0 && o < 1)
                                : sameGroupOrders.filter(o => o >= 1);

                            if (zoneOrders.length > 1) {
                                canStepUp = numericOrder > Math.min(...zoneOrders);
                                canStepDown = numericOrder < Math.max(...zoneOrders);
                            }
                        }

                        const isDraggable = isAdmin && !hasMultipleAssignees;

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-1 py-0.5 whitespace-normal text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 dark:border-slate-600 text-gray-900 dark:text-slate-100 ${columnClass}`}
                                style={customStyle}
                                title={cellValue}
                                draggable={isDraggable}
                            >
                                <div className="flex items-center gap-1">
                                    {canStep && onStepOrder && (
                                        <div className="flex flex-col flex-shrink-0">
                                            <button
                                                onClick={(e) => { e.stopPropagation(); if (canStepUp) onStepOrder(submittalId, 'up'); }}
                                                disabled={!canStepUp}
                                                className={`text-xs leading-none px-0.5 rounded transition-colors ${canStepUp ? 'text-accent-600 hover:text-accent-800 hover:bg-accent-50 cursor-pointer' : 'text-gray-300 dark:text-slate-600 cursor-not-allowed'}`}
                                                title={canStepUp ? 'Move up' : 'Already at top of zone'}
                                            >▲</button>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); if (canStepDown) onStepOrder(submittalId, 'down'); }}
                                                disabled={!canStepDown}
                                                className={`text-xs leading-none px-0.5 rounded transition-colors ${canStepDown ? 'text-accent-600 hover:text-accent-800 hover:bg-accent-50 cursor-pointer' : 'text-gray-300 dark:text-slate-600 cursor-not-allowed'}`}
                                                title={canStepDown ? 'Move down' : 'Already at bottom of zone'}
                                            >▼</button>
                                        </div>
                                    )}
                                    <span className={`text-center flex-1 ${isDraggable ? 'cursor-grab active:cursor-grabbing' : ''}`}>{cellValue}</span>
                                </div>
                            </td>
                        );
                    }

                    // Handle PROJ. # column - make it a link to Procore
                    const isProjectNumber = column === 'PROJ. #';
                    if (isProjectNumber) {
                        const submittalId = row.submittal_id || row['Submittals Id'] || '';
                        const projectId = row.procore_project_id || row['Project Id'] || '';
                        const procoreUrl = projectId && submittalId
                            ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}`
                            : null;

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 dark:border-slate-600 text-center dwl-col-project-number`}
                                style={{ maxWidth: '65px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                                title={procoreUrl ? `${cellValue} - Click to open in Procore` : cellValue}
                            >
                                {procoreUrl ? (
                                    <a
                                        href={procoreUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline cursor-pointer transition-colors"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        {cellValue}
                                    </a>
                                ) : (
                                    <span className="text-gray-900 dark:text-slate-100">{cellValue}</span>
                                )}
                            </td>
                        );
                    }

                    // Determine if this column should allow text wrapping
                    const shouldWrap = column === 'NOTES';
                    const whitespaceClass = shouldWrap ? 'whitespace-normal' : 'whitespace-nowrap';

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-1 py-0.5 ${whitespaceClass} text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 dark:border-slate-600 text-gray-900 dark:text-slate-100 ${customWidthClass} ${columnClass} text-center`}
                            style={customStyle}
                            title={cellValue}
                        >
                            {cellValue}
                        </td>
                    );
                })}
            </tr>
        </>
    );
}

