import React, { useState, useEffect } from 'react';
import { jobsApi } from '../services/jobsApi';
import { JobDetailsModal } from './JobDetailsModal';

export function JobsTableRow({ row, columns, formatCellValue, formatDate, rowIndex, onDragStart, onDragOver, onDragLeave, onDrop, isDragging, dragOverIndex, onUpdate }) {
    const [isModalOpen, setIsModalOpen] = useState(false);

    // Alternate row background colors with higher contrast
    const rowBgClass = rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-200';

    // Row is draggable (disabled for now)
    const isDraggable = false;

    // Stage options with simplified names for display (in progression order)
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Cut start', label: 'Cut start' },
        { value: 'Fit Up Complete.', label: 'Fitup comp' },
        { value: 'Welded QC', label: 'Welded QC' },
        { value: 'Paint complete', label: 'Paint comp' },
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
            light: 'rgb(219 234 254)', // blue-100
            base: 'rgb(59 130 246)', // blue-500
            dark: 'rgb(37 99 235)', // blue-600
            text: 'rgb(30 64 175)', // blue-800
            border: 'rgb(147 197 253)', // blue-300
            className: 'bg-blue-100 text-blue-800 border-blue-300'
        },
        'Paint complete': {
            light: 'rgb(254 249 195)', // yellow-100
            base: 'rgb(234 179 8)', // yellow-500
            dark: 'rgb(202 138 4)', // yellow-600
            text: 'rgb(133 77 14)', // yellow-800
            border: 'rgb(253 224 71)', // yellow-300
            className: 'bg-yellow-100 text-yellow-800 border-yellow-300'
        },
        'Store at MHMW for shipping': {
            light: 'rgb(254 249 195)', // yellow-100
            base: 'rgb(234 179 8)', // yellow-500
            dark: 'rgb(202 138 4)', // yellow-600
            text: 'rgb(133 77 14)', // yellow-800
            border: 'rgb(253 224 71)', // yellow-300
            className: 'bg-yellow-100 text-yellow-800 border-yellow-300'
        },
        'Shipping planning': {
            light: 'rgb(254 249 195)', // yellow-100
            base: 'rgb(234 179 8)', // yellow-500
            dark: 'rgb(202 138 4)', // yellow-600
            text: 'rgb(133 77 14)', // yellow-800
            border: 'rgb(253 224 71)', // yellow-300
            className: 'bg-yellow-100 text-yellow-800 border-yellow-300'
        },
        'Shipping completed': {
            light: 'rgb(209 250 229)', // emerald-100
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        },
        'Complete': {
            light: 'rgb(209 250 229)', // emerald-100
            base: 'rgb(16 185 129)', // emerald-500
            dark: 'rgb(5 150 105)', // emerald-600
            text: 'rgb(6 95 70)', // emerald-800
            border: 'rgb(110 231 183)', // emerald-300
            className: 'bg-emerald-100 text-emerald-800 border-emerald-300'
        }
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

    // Sync local state when row data changes (e.g., on refresh)
    useEffect(() => {
        setLocalStage(row['Stage'] || 'Released');
        setLocalFabOrder(row['Fab Order'] ?? '');
        setFabOrderInputValue(row['Fab Order'] ?? '');
        setLocalNotes(row['Notes'] ?? '');
        setNotesInputValue(row['Notes'] ?? '');
    }, [row['Stage'], row['Fab Order'], row['Notes']]);

    // Handle stage change
    const handleStageChange = async (newStage) => {
        const oldStage = localStage;
        setLocalStage(newStage); // Optimistic update
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
            alert(`Failed to update stage: ${error.message}`);
        } finally {
            setUpdatingStage(false);
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

        // Check if drag started from a protected cell (Fab Order, Stage, Notes)
        const target = e.target;
        const cell = target.closest('td');

        if (cell) {
            const cellClasses = cell.className || '';
            const isFabOrderCell = cell.querySelector('input[type="text"]') !== null ||
                cell.querySelector('input[type="number"]') !== null;
            const isStageCell = cell.querySelector('select') !== null;
            const isNotesCell = cell.querySelector('textarea') !== null;

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

            if (isFabOrderCell || isStageCell || isNotesCell || isInputElement) {
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
                className={`${rowBgClass} hover:bg-gray-100 transition-all duration-200 border-b border-gray-300 ${isDragOver ? 'bg-blue-50' : ''} ${isBeingDragged ? 'opacity-40 scale-[0.98] shadow-lg' : ''} ${isDragOver ? 'ring-2 ring-blue-400 ring-inset' : ''}`}
                draggable={isDraggable}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragLeave={onDragLeave}
                onDrop={handleDrop}
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

                    // Handle Stage column with editable color-coded dropdown
                    if (column === 'Stage') {
                        const currentStageColors = stageColors[localStage] || stageColors['Released'];
                        // Get display label for current stage
                        const currentOption = stageOptions.find(opt => opt.value === localStage);
                        const currentLabel = currentOption ? currentOption.label : localStage;

                        // Solid color style (no gradient)
                        const solidStyle = {
                            backgroundColor: currentStageColors.light,
                            color: currentStageColors.text,
                            borderColor: currentStageColors.border
                        };

                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 text-center`}
                                style={{ minWidth: '140px' }}
                                draggable={false}
                                onMouseDown={handleProtectedCellMouseDown}
                            >
                                <select
                                    value={localStage}
                                    onChange={(e) => handleStageChange(e.target.value)}
                                    disabled={updatingStage}
                                    className={`w-full px-2 py-0.5 text-[10px] border-2 rounded font-medium focus:outline-none focus:ring-2 focus:ring-offset-1 text-center transition-all relative overflow-hidden ${updatingStage ? 'opacity-50 cursor-wait' : ''}`}
                                    style={{
                                        minWidth: '120px',
                                        ...solidStyle
                                    }}
                                >
                                    {stageOptions.map((option) => {
                                        const optionColors = stageColors[option.value] || stageColors['Released'];
                                        return (
                                            <option
                                                key={option.value}
                                                value={option.value}
                                                style={{
                                                    backgroundColor: optionColors.light,
                                                    color: optionColors.text
                                                }}
                                            >
                                                {option.label}
                                            </option>
                                        );
                                    })}
                                </select>
                            </td>
                        );
                    }

                    // Handle Fab Order column with editable input
                    if (column === 'Fab Order') {
                        const displayValue = localFabOrder === null || localFabOrder === undefined ? '—' : formatCellValue(localFabOrder, column);
                        return (
                            <td
                                key={`${row.id}-${column}`}
                                className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 text-center`}
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
                                    className={`w-full px-1 py-0.5 text-[10px] border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900 text-center ${updatingFabOrder ? 'opacity-50 cursor-wait' : ''}`}
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
                                className={`${paddingClass} py-0.5 text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 text-center whitespace-normal`}
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
                                    className={`w-full px-1 py-0.5 text-[10px] border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900 resize-none ${updatingNotes ? 'opacity-50 cursor-wait' : ''}`}
                                    placeholder="—"
                                    rows={2}
                                    style={{ minWidth: '120px' }}
                                />
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
                                className={`${paddingClass} py-0.5 text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 text-center cursor-pointer hover:bg-accent-50 transition-colors`}
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
                                    <span className="text-blue-600 hover:text-blue-800 hover:underline">
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
                                    className={`${paddingClass} py-0.5 text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 text-center`}
                                    title={`${rawValue} - Click to open Procore viewer`}
                                >
                                    <a
                                        href={viewerUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
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
                            className={`${paddingClass} py-0.5 text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 text-center ${shouldWrapAndTruncate
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
            </tr>
            <JobDetailsModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                job={row}
            />
        </>
    );
}

