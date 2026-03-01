import React, { useState, useEffect, useRef } from 'react';
import { formatDate, formatDateShort } from '../utils/formatters';
import { JUMP_TO_HIGHLIGHT_CLASS } from '../constants/jumpToHighlight';

export function TableRow({ row, columns, formatCellValue, formatDate, onOrderNumberChange, onNotesChange, onStatusChange, onProcoreStatusChange, procoreStatusOptions, selectedTab, onBump, onDueDateChange, rowIndex, onDragStart, onDragOver, onDragLeave, onDrop, isDragging, dragOverIndex, isAdmin = false, isJumpToHighlight }) {
    const [editingOrderNumber, setEditingOrderNumber] = useState(false);
    const [orderNumberValue, setOrderNumberValue] = useState('');
    const [editingNotes, setEditingNotes] = useState(false);
    const [notesValue, setNotesValue] = useState('');
    const [editingDueDate, setEditingDueDate] = useState(false);
    const [dueDateValue, setDueDateValue] = useState('');
    const inputRef = useRef(null);
    const notesInputRef = useRef(null);
    const dueDateInputRef = useRef(null);

    const submittalId = row['Submittals Id'] || row.submittal_id;
    const ballInCourt = row.ball_in_court ?? row['BIC'] ?? '';
    const hasMultipleAssignees = String(ballInCourt).includes(',');
    const isDraggable = isAdmin && !hasMultipleAssignees;

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
        // Only allow editing if user is admin
        if (!isAdmin) {
            return;
        }
        const currentValue = row['NOTES'] ?? row.notes ?? '';
        setNotesValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
        setEditingNotes(true);
    };

    const handleNotesBlur = () => {
        setEditingNotes(false);
        if (submittalId && onNotesChange) {
            onNotesChange(submittalId, notesValue);
        }
    };

    const handleNotesKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            e.target.blur();
        } else if (e.key === 'Escape') {
            const currentValue = row['NOTES'] ?? row.notes ?? '';
            setNotesValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
            setEditingNotes(false);
        }
    };

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
        // Only allow editing if user is admin
        if (!isAdmin) {
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
    const baseRowBgClass = rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-200';
    const rowBgClass = isHoldStatus ? 'bg-yellow-200' : baseRowBgClass;

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

    // Drag and drop handlers
    const handleDragStart = (e) => {
        if (!isDraggable) {
            e.preventDefault();
            return;
        }

        // Check if drag started from a protected cell (Order Number, Project Number, Procore Status, Status, Notes, Due Date)
        const target = e.target;
        const cell = target.closest('td');

        if (cell) {
            const cellClasses = cell.className || '';
            const isOrderNumberCell = cellClasses.includes('dwl-col-order-number');
            const isProjectNumberCell = cellClasses.includes('dwl-col-project-number');
            const isProcoreStatusCell = cellClasses.includes('dwl-col-procore-status');
            const isStatusCell = cellClasses.includes('dwl-col-comp-status');
            const isNotesCell = cellClasses.includes('dwl-col-notes');
            const isDueDateCell = cellClasses.includes('dwl-col-due-date');

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

            if (isOrderNumberCell || isProjectNumberCell || isProcoreStatusCell || isStatusCell || isNotesCell || isDueDateCell || isInputElement) {
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
                className={`${rowBgClass} hover:bg-gray-100 transition-all duration-200 border-b border-gray-300 ${isDragOver ? 'bg-blue-50' : ''} ${isBeingDragged ? 'opacity-40 scale-[0.98] shadow-lg' : ''} ${isDragOver ? 'ring-2 ring-blue-400 ring-inset' : ''} ${isJumpToHighlight ? JUMP_TO_HIGHLIGHT_CLASS : ''}`}
                draggable={isDraggable}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragLeave={onDragLeave}
                onDrop={handleDrop}
                data-submittal-id={submittalId}
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
                                className={`px-0.5 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 text-center dwl-col-order-number`}
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
                                    className="w-full px-0.5 py-0 text-xs border-2 border-accent-500 rounded-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white font-medium text-gray-900"
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

                        // Check if order number is an integer >= 1 and has ball_in_court (eligible for bump)
                        // Also requires admin privileges
                        const canBump = isAdmin && rawOrderValue !== null && rawOrderValue !== undefined && rawOrderValue !== '' && 
                                       typeof rawOrderValue === 'number' && rawOrderValue >= 1 && rawOrderValue === Math.floor(rawOrderValue) &&
                                       ballInCourt && !hasMultipleAssignees;

                        const handleBumpClick = (e) => {
                            e.stopPropagation();
                            if (submittalId && onBump && canBump) {
                                onBump(submittalId);
                            }
                        };

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 text-center dwl-col-order-number`}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <div className="flex items-center justify-center gap-1">
                                    <div 
                                        className={`px-0.5 py-0 text-xs border rounded-sm font-medium min-w-[20px] max-w-[50px] inline-block transition-colors ${isEditable
                                            ? 'border-gray-300 bg-gray-50 hover:bg-white hover:border-accent-400 cursor-text text-gray-700'
                                            : 'border-gray-200 bg-gray-100 cursor-not-allowed text-gray-500 opacity-75'
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
                                            title="Bump submittal to 0.9 urgency slot"
                                        >
                                            Bump
                                        </button>
                                    )}
                                </div>
                            </td>
                        );
                    }

                    if (isNotes && editingNotes) {
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dwl-col-notes`}
                                style={{ maxWidth: '350px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <textarea
                                    ref={notesInputRef}
                                    value={notesValue}
                                    onChange={(e) => setNotesValue(e.target.value)}
                                    onBlur={handleNotesBlur}
                                    onKeyDown={handleNotesKeyDown}
                                    className="w-full px-1 py-0.5 text-xs border-2 border-accent-500 rounded-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white text-gray-900 resize-none shadow-sm transition-all text-center"
                                    rows={1}
                                    placeholder="Add notes..."
                                    style={{ lineHeight: '1.5' }}
                                />
                            </td>
                        );
                    }

                    if (isNotes) {
                        const hasNotes = cellValue && cellValue !== '—';
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dwl-col-notes`}
                                style={{ maxWidth: '350px' }}
                                draggable={false}
                                onClick={isAdmin ? handleNotesFocus : undefined}
                                onMouseDown={handleProtectedCellMouseDown}
                                title={isAdmin ? "Click to edit notes" : "Read-only (admin only)"}
                            >
                                <div className={`px-0.5 py-0 text-xs rounded-sm border transition-all min-h-[10px] text-center ${
                                    isAdmin 
                                        ? hasNotes
                                            ? 'border-gray-200 bg-gray-50 hover:bg-white hover:border-accent-300 hover:shadow-sm text-gray-800 cursor-text'
                                            : 'border-gray-200 bg-gray-50/50 hover:bg-gray-100 hover:border-accent-300 text-gray-500 cursor-text'
                                        : hasNotes
                                            ? 'border-gray-200 bg-gray-100 text-gray-600 cursor-default'
                                            : 'border-gray-200 bg-gray-50/50 text-gray-400 cursor-default'
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
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dwl-col-procore-status`}
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
                                        className="w-full px-0.5 py-0.5 text-xs border border-gray-300 rounded text-center bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 cursor-pointer"
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
                                    <span className="text-xs text-gray-700">{currentProcoreStatus || '—'}</span>
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
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dwl-col-status`}
                                style={{ maxWidth: '96px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <select
                                    value={currentStatus || ''}
                                    onChange={(e) => {
                                        if (isAdmin && submittalId && onStatusChange) {
                                            onStatusChange(submittalId, e.target.value);
                                        }
                                    }}
                                    disabled={!isAdmin}
                                    className={`w-full px-0.5 py-0.5 text-xs border border-gray-300 rounded text-center ${
                                        isAdmin 
                                            ? 'bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 cursor-pointer'
                                            : 'bg-gray-100 text-gray-600 cursor-not-allowed opacity-75'
                                    }`}
                                    title={isAdmin ? "Select drafting status (HOLD / NEED VIF / STARTED)" : "Read-only (admin only)"}
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
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dwl-col-due-date`}
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
                                    className="w-full px-0.5 py-0 text-xs border-2 border-accent-500 rounded-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white font-medium text-gray-900"
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
                                className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300 dwl-col-due-date`}
                                style={{ maxWidth: '120px' }}
                                draggable={false}
                                onClick={isAdmin ? handleDueDateFocus : undefined}
                                onMouseDown={handleProtectedCellMouseDown}
                                title={isAdmin ? "Click to edit due date" : "Read-only (admin only)"}
                            >
                                <div className={`px-0.5 py-0 text-xs rounded-sm border transition-all min-h-[10px] text-center ${
                                    isAdmin
                                        ? hasDueDate
                                            ? 'border-red-300 bg-red-100 hover:bg-red-200 hover:border-red-400 text-red-900 font-medium cursor-text'
                                            : 'border-gray-200 bg-gray-50/50 hover:bg-gray-100 hover:border-accent-300 text-gray-500 cursor-text'
                                        : hasDueDate
                                            ? 'border-red-200 bg-red-50 text-red-700 font-medium cursor-default'
                                            : 'border-gray-200 bg-gray-50/50 text-gray-400 cursor-default'
                                }`}>
                                    {hasDueDate ? formattedDate : <span className="italic">{isAdmin ? "Click to add..." : "—"}</span>}
                                </div>
                            </td>
                        );
                    }

                    // Apply light green background for Type cell when type is "Drafting Release Review"
                    const cellBgClass = isType && isDraftingReleaseReview
                        ? 'bg-green-100'
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
                                className={`px-1 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 text-center dwl-col-name`}
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
                                className={`px-1 py-0.5 ${whitespaceClass} text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 text-center dwl-col-bic`}
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
                                bgColorClass = 'bg-red-200'; // Red for 5+ days
                            } else if (daysSinceUpdate >= 3) {
                                bgColorClass = 'bg-yellow-200'; // Yellow for 3-4 days
                            }
                        }

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-1 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${bgColorClass || cellBgClass} border-r border-gray-300 text-center dwl-col-last-bic`}
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
                                className={`px-0 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 text-center dwl-col-lifespan`}
                                style={{ maxWidth: '75px' }}
                                title={lifespanValue !== null && lifespanValue !== undefined ? `${lifespanValue} days since creation` : 'N/A'}
                            >
                                {displayLifespan}
                            </td>
                        );
                    }

                    // Handle TITLE column - plain text display
                    if (column === 'TITLE') {
                        const shouldWrap = true;
                        const whitespaceClass = 'whitespace-normal';

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`px-1 py-0.5 ${whitespaceClass} text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 ${columnClass} text-center`}
                                style={customStyle}
                                title={cellValue}
                            >
                                {cellValue}
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
                                className={`px-0.5 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 text-center dwl-col-project-number`}
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
                                        className="text-blue-600 hover:text-blue-800 hover:underline cursor-pointer transition-colors"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        {cellValue}
                                    </a>
                                ) : (
                                    <span>{cellValue}</span>
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
                            className={`px-1 py-0.5 ${whitespaceClass} text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 ${customWidthClass} ${columnClass} text-center`}
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

