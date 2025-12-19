import React, { useState, useEffect, useRef } from 'react';

export function TableRow({ row, columns, formatCellValue, formatDate, onOrderNumberChange, onNotesChange, onStatusChange, rowIndex, onDragStart, onDragOver, onDrop, isDragging, dragOverIndex }) {
    const [editingOrderNumber, setEditingOrderNumber] = useState(false);
    const [orderNumberValue, setOrderNumberValue] = useState('');
    const [editingNotes, setEditingNotes] = useState(false);
    const [notesValue, setNotesValue] = useState('');
    const inputRef = useRef(null);
    const notesInputRef = useRef(null);

    const submittalId = row['Submittals Id'] || row.submittal_id;
    const ballInCourt = row.ball_in_court ?? row['Ball In Court'] ?? '';
    const hasMultipleAssignees = String(ballInCourt).includes(',');
    const isDraggable = !hasMultipleAssignees;

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
        // Check if this row has multiple assignees (comma-separated ball_in_court)
        const ballInCourt = row.ball_in_court ?? row['Ball In Court'] ?? '';
        const hasMultipleAssignees = String(ballInCourt).includes(',');

        // Don't allow editing order number for multiple assignees (reviewers)
        if (hasMultipleAssignees) {
            return;
        }

        const currentValue = row['Order Number'] ?? row.order_number ?? '';
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
            const currentValue = row['Order Number'] ?? row.order_number ?? '';
            setOrderNumberValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
            setEditingOrderNumber(false);
        }
    };

    const handleNotesFocus = () => {
        const currentValue = row['Notes'] ?? row.notes ?? '';
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
            const currentValue = row['Notes'] ?? row.notes ?? '';
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

    const rowType = row.type ?? row['Type'] ?? '';
    const isDraftingReleaseReview = rowType === 'Drafting Release Review';

    // Alternate row background colors
    const rowBgClass = rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-200';

    // Drag and drop handlers
    const handleDragStart = (e) => {
        if (!isDraggable) {
            e.preventDefault();
            return;
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
        <tr
            className={`${rowBgClass} hover:bg-gray-100 transition-colors duration-150 border-b border-gray-300 ${isDragOver ? 'bg-accent-100' : ''} ${isBeingDragged ? 'opacity-50' : ''}`}
            draggable={isDraggable}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
        >
            {/* Ellipsis indicator column - far left */}
            <td
                className={`px-0.5 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 text-center`}
                style={{ width: '32px' }}
            >
                <div
                    className={`flex flex-col items-center justify-center w-6 h-6 rounded transition-colors pointer-events-none ${isDraggable ? '' : 'opacity-50'}`}
                    title={isDraggable ? "Drag row to reorder" : "Cannot reorder (multiple assignees)"}
                >
                    <div className="flex flex-col items-center gap-0.5">
                        <div className="w-1 h-1 rounded-full bg-gray-400"></div>
                        <div className="w-1 h-1 rounded-full bg-gray-400"></div>
                        <div className="w-1 h-1 rounded-full bg-gray-400"></div>
                    </div>
                </div>
            </td>
            {columns.map((column) => {
                const isOrderNumber = column === 'Order Number';
                const isSubmittalId = column === 'Submittals Id';
                const isType = column === 'Type';
                const isNotes = column === 'Notes';
                const isStatus = column === 'Status';
                const isProjectName = column === 'Project Name';
                const isBallInCourt = column === 'Ball In Court';

                // Custom width for Submittals Id and Project Number
                let customWidthClass = '';
                let customStyle = {};
                if (isSubmittalId) {
                    customWidthClass = 'w-24'; // Accommodate 8-10 digit ID
                } else if (column === 'Project Number') {
                    customWidthClass = 'w-20'; // Accommodate 3-4 digit number
                } else if (column === 'Title') {
                    // Use max-width instead of fixed width for better 4K support
                    customStyle = { maxWidth: '320px', width: '320px' };
                } else if (column === 'Type') {
                    customStyle = { maxWidth: '80px', width: '80px' };
                } else if (column === 'Submittal Manager') {
                    customWidthClass = 'w-32'; // Reduce Submittal Manager width
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
                            className={`px-0.5 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 text-center`}
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
                    // isEditable already determined above (hasMultipleAssignees)
                    const isEditable = !hasMultipleAssignees;

                    // Display Order Number - show all values (including decimals and numbers > 10)
                    const rawOrderValue = row['Order Number'] ?? row.order_number;
                    let displayOrder = '';

                    if (rawOrderValue !== null && rawOrderValue !== undefined && rawOrderValue !== '') {
                        const numericOrder = typeof rawOrderValue === 'number'
                            ? rawOrderValue
                            : parseFloat(rawOrderValue);

                        if (!Number.isNaN(numericOrder)) {
                            displayOrder = String(numericOrder);
                        }
                    }

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-0.5 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 text-center`}
                            onClick={isEditable ? handleOrderNumberFocus : undefined}
                            title={isEditable ? "Click to edit order number" : "Order number editing disabled for multiple assignees (reviewers)"}
                        >
                            <div className={`px-0.5 py-0 text-xs border rounded-sm font-medium min-w-[20px] max-w-[50px] inline-block transition-colors ${isEditable
                                ? 'border-gray-300 bg-gray-50 hover:bg-white hover:border-accent-400 cursor-text text-gray-700'
                                : 'border-gray-200 bg-gray-100 cursor-not-allowed text-gray-500 opacity-75'
                                }`}>
                                {displayOrder}
                            </div>
                        </td>
                    );
                }

                if (isNotes && editingNotes) {
                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300`}
                            style={{ maxWidth: '350px', width: '350px' }}
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
                            className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300`}
                            style={{ maxWidth: '350px', width: '350px' }}
                            onClick={handleNotesFocus}
                            title="Click to edit notes"
                        >
                            <div className={`px-0.5 py-0 text-xs rounded-sm border transition-all cursor-text min-h-[10px] text-center ${hasNotes
                                ? 'border-gray-200 bg-gray-50 hover:bg-white hover:border-accent-300 hover:shadow-sm text-gray-800'
                                : 'border-gray-200 bg-gray-50/50 hover:bg-gray-100 hover:border-accent-300 text-gray-500'
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

                if (isSubmittalId && cellValue !== '—') {
                    const projectId = row['Project Id'] ?? row.procore_project_id ?? '';
                    const submittalId = row['Submittals Id'] ?? row.submittal_id ?? '';
                    const href = projectId && submittalId
                        ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}`
                        : '#';

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-0.5 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${rowBgClass} border-r border-gray-300 ${customWidthClass} text-center`}
                            title={cellValue}
                        >
                            {href !== '#' ? (
                                <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-blue-600 hover:text-blue-800 underline font-semibold inline-flex items-center gap-1 text-xs"
                                >
                                    <span>{cellValue}</span>
                                </a>
                            ) : (
                                <span className="text-gray-900 text-xs">{cellValue}</span>
                            )}
                        </td>
                    );
                }

                if (isStatus) {
                    const currentStatus = row.submittal_drafting_status ?? row['Submittal Drafting Status'] ?? '';
                    const statusOptions = ['STARTED', 'NEED VIF', 'HOLD'];

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-0.5 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300`}
                            style={{ width: '90px' }}
                        >
                            <select
                                value={currentStatus || ''}
                                onChange={(e) => {
                                    if (submittalId && onStatusChange) {
                                        // Send empty string for blank, not null
                                        onStatusChange(submittalId, e.target.value);
                                    }
                                }}
                                className="w-full px-0.5 py-0.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 text-center"
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

                // Apply light green background for Type cell when type is "Drafting Release Review"
                const cellBgClass = isType && isDraftingReleaseReview
                    ? 'bg-green-100'
                    : rowBgClass;

                // Handle Project Name truncation to 20 characters
                if (isProjectName) {
                    const fullProjectName = cellValue;
                    const truncatedProjectName = fullProjectName && fullProjectName.length > 20
                        ? fullProjectName.substring(0, 20) + '...'
                        : fullProjectName;

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-1 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 text-center`}
                            style={{ maxWidth: '280px', width: '280px' }}
                            title={fullProjectName}
                        >
                            {truncatedProjectName}
                        </td>
                    );
                }

                // Handle Ball In Court: wrap if value is longer than 'Rourke Alvarado' (15 chars)
                if (isBallInCourt) {
                    // Get the value directly from row to ensure we have it
                    const ballInCourtValue = row.ball_in_court ?? row['Ball In Court'] ?? rawValue ?? '';
                    const ballInCourtString = String(ballInCourtValue);
                    const shouldWrap = ballInCourtString.length > 15; // 'Rourke Alvarado' is 15 chars
                    const whitespaceClass = shouldWrap ? 'whitespace-normal break-words' : 'whitespace-nowrap';

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-1 py-0.5 ${whitespaceClass} text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 text-center`}
                            style={{ maxWidth: '180px', width: '180px' }}
                            title={cellValue}
                        >
                            {cellValue}
                        </td>
                    );
                }

                // Determine if this column should allow text wrapping
                const shouldWrap = column === 'Title' || column === 'Notes';
                const whitespaceClass = shouldWrap ? 'whitespace-normal' : 'whitespace-nowrap';

                return (
                    <td
                        key={`${row.id}-${column}`}
                        className={`px-1 py-0.5 ${whitespaceClass} text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 ${customWidthClass} text-center`}
                        style={customStyle}
                        title={cellValue}
                    >
                        {cellValue}
                    </td>
                );
            })}
        </tr>
    );
}

