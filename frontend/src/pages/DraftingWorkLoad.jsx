import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useDataFetching } from '../hooks/useDataFetching';
import { useMutations } from '../hooks/useMutations';
import { useFilters } from '../hooks/useFilters';
import { TableRow } from '../components/TableRow';
import { generateDraftingWorkLoadPDF } from '../utils/pdfUtils';

function DraftingWorkLoad() {
    const { submittals, columns, loading, error: fetchError, lastUpdated, refetch } = useDataFetching();
    const {
        updateOrderNumber,
        updateNotes,
        updateStatus,
        uploadFile,
        uploading,
        uploadError,
        uploadSuccess,
        clearUploadSuccess,
        updating,
        error: mutationError,
        success
    } = useMutations(refetch);

    const rows = submittals; // now that submittals is clean, we alias

    // Use the filters hook
    const {
        selectedBallInCourt,
        selectedSubmittalManager,
        selectedProjectName,
        projectNameSortMode,
        setSelectedBallInCourt,
        setSelectedSubmittalManager,
        setSelectedProjectName,
        ballInCourtOptions,
        submittalManagerOptions,
        projectNameOptions,
        displayRows,
        resetFilters,
        handleProjectNameSortToggle,
        ALL_OPTION_VALUE,
    } = useFilters(rows);

    // Drag and drop state
    const [draggedIndex, setDraggedIndex] = useState(null);
    const [dragOverIndex, setDragOverIndex] = useState(null);
    const [draggedRow, setDraggedRow] = useState(null);

    /**
     * Calculate a new "top bump" order number when moving a row above the current #1
     * for a given ball_in_court group.
     *
     * Rules:
     * - If the smallest order >= 1, use 0.5
     * - If there are already decimals < 1, keep halving the current smallest positive order
     */
    const calculateTopOrderNumber = useCallback((draggedRow, allRows) => {
        const draggedBallInCourt = draggedRow.ball_in_court ?? draggedRow['Ball In Court'] ?? '';

        // Filter rows to only those with the same ball_in_court (use all rows, not just filtered)
        const sameBallInCourtRows = allRows.filter(row => {
            const rowBallInCourt = row.ball_in_court ?? row['Ball In Court'] ?? '';
            return String(rowBallInCourt) === String(draggedBallInCourt);
        });

        if (sameBallInCourtRows.length === 0) {
            return 0.5;
        }

        // Sort by current order number
        const sortedRows = [...sameBallInCourtRows].sort((a, b) => {
            const orderA = a.order_number ?? a['Order Number'] ?? 999999;
            const orderB = b.order_number ?? b['Order Number'] ?? 999999;
            return orderA - orderB;
        });

        const first = sortedRows[0];
        const firstOrderRaw = first.order_number ?? first['Order Number'] ?? 1;
        const firstOrder = typeof firstOrderRaw === 'number' ? firstOrderRaw : parseFloat(firstOrderRaw) || 1;

        // If the first order is an integer >= 1, just use 0.5
        if (firstOrder >= 1) {
            return 0.5;
        }

        // Otherwise, find the smallest positive order and halve it
        let minPositive = Infinity;
        for (const row of sortedRows) {
            const raw = row.order_number ?? row['Order Number'];
            if (raw === null || raw === undefined) continue;
            const val = typeof raw === 'number' ? raw : parseFloat(raw);
            if (!isNaN(val) && val > 0 && val < minPositive) {
                minPositive = val;
            }
        }

        const base = minPositive === Infinity ? 1 : minPositive;
        const newOrder = base / 2;

        // Round to reasonable precision (4 decimal places)
        return Math.round(newOrder * 10000) / 10000;
    }, []);

    // Drag handlers
    const handleDragStart = useCallback((e, index, row) => {
        setDraggedIndex(index);
        setDraggedRow(row);
    }, []);

    const handleDragOver = useCallback((e, index) => {
        e.preventDefault();
        if (draggedRow) {
            const targetRow = displayRows[index];
            const draggedBallInCourt = draggedRow.ball_in_court ?? draggedRow['Ball In Court'] ?? '';
            const targetBallInCourt = targetRow.ball_in_court ?? targetRow['Ball In Court'] ?? '';

            // Only allow drag over if same ball_in_court
            if (String(draggedBallInCourt) === String(targetBallInCourt)) {
                setDragOverIndex(index);
            }
        }
    }, [draggedRow, displayRows]);

    const handleDrop = useCallback(async (e, targetIndex, targetRow) => {
        e.preventDefault();

        if (!draggedRow) return;

        const draggedBallInCourt = draggedRow.ball_in_court ?? draggedRow['Ball In Court'] ?? '';
        const targetBallInCourt = targetRow.ball_in_court ?? targetRow['Ball In Court'] ?? '';

        // Only allow drop if same ball_in_court
        if (String(draggedBallInCourt) !== String(targetBallInCourt)) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            setDraggedRow(null);
            return;
        }

        // Work with all rows in this ball_in_court group, sorted by current order
        const draggedRowId = draggedRow['Submittals Id'] || draggedRow.submittal_id;
        const targetRowId = targetRow['Submittals Id'] || targetRow.submittal_id;

        const sameBallInCourtRows = rows.filter(row => {
            const rowBallInCourt = row.ball_in_court ?? row['Ball In Court'] ?? '';
            return String(rowBallInCourt) === String(draggedBallInCourt);
        });

        const sortedGroup = [...sameBallInCourtRows].sort((a, b) => {
            const orderA = a.order_number ?? a['Order Number'] ?? 999999;
            const orderB = b.order_number ?? b['Order Number'] ?? 999999;
            return orderA - orderB;
        });

        const draggedPosition = sortedGroup.findIndex(r => {
            const rowId = r['Submittals Id'] || r.submittal_id;
            return rowId === draggedRowId;
        });

        const targetPosition = sortedGroup.findIndex(r => {
            const rowId = r['Submittals Id'] || r.submittal_id;
            return rowId === targetRowId;
        });

        if (draggedPosition === -1 || targetPosition === -1) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            setDraggedRow(null);
            return;
        }

        const submittalId = draggedRowId;

        // Case 1: moving above the current first item -> use decimal bumping
        if (targetPosition === 0 && draggedPosition !== 0) {
            const newOrderNumber = calculateTopOrderNumber(draggedRow, rows);
            if (submittalId) {
                await updateOrderNumber(submittalId, newOrderNumber);
            }
        } else {
            // Case 2: reordering in the middle or end -> renumber entire group to 1, 2, 3, ...

            // Remove dragged row from group
            const groupWithoutDragged = sortedGroup.filter(r => {
                const rowId = r['Submittals Id'] || r.submittal_id;
                return rowId !== draggedRowId;
            });

            // Find target index in the reduced group
            const targetIndexInReduced = groupWithoutDragged.findIndex(r => {
                const rowId = r['Submittals Id'] || r.submittal_id;
                return rowId === targetRowId;
            });

            if (targetIndexInReduced === -1) {
                setDraggedIndex(null);
                setDragOverIndex(null);
                setDraggedRow(null);
                return;
            }

            // Determine insert position: if dragging down, insert after target; if up, before target
            let insertPosition;
            if (draggedPosition < targetPosition) {
                insertPosition = targetIndexInReduced + 1;
            } else {
                insertPosition = targetIndexInReduced;
            }

            const clampedInsert = Math.max(0, Math.min(insertPosition, groupWithoutDragged.length));

            const reorderedGroup = [
                ...groupWithoutDragged.slice(0, clampedInsert),
                draggedRow,
                ...groupWithoutDragged.slice(clampedInsert),
            ];

            // Renumber group while preserving meaning of decimal "urgent" orders:
            // - A contiguous prefix of rows whose current order < 1 keep their decimal values
            // - Everything after that prefix is renumbered to 1, 2, 3, ... based on new order
            let urgentPrefixLength = 0;

            for (let i = 0; i < reorderedGroup.length; i++) {
                const row = reorderedGroup[i];
                const currentOrderRaw = row.order_number ?? row['Order Number'] ?? null;
                const currentOrder = typeof currentOrderRaw === 'number'
                    ? currentOrderRaw
                    : currentOrderRaw !== null && currentOrderRaw !== undefined
                        ? parseFloat(currentOrderRaw)
                        : null;

                if (currentOrder !== null && !isNaN(currentOrder) && currentOrder > 0 && currentOrder < 1) {
                    urgentPrefixLength += 1;
                } else {
                    break;
                }
            }

            let nextIntegerOrder = 1;

            for (let i = 0; i < reorderedGroup.length; i++) {
                const row = reorderedGroup[i];
                const rowId = row['Submittals Id'] || row.submittal_id;
                const currentOrderRaw = row.order_number ?? row['Order Number'] ?? null;
                const currentOrder = typeof currentOrderRaw === 'number'
                    ? currentOrderRaw
                    : currentOrderRaw !== null && currentOrderRaw !== undefined
                        ? parseFloat(currentOrderRaw)
                        : null;

                let newOrderNumber;

                if (i < urgentPrefixLength && currentOrder !== null && !isNaN(currentOrder) && currentOrder > 0 && currentOrder < 1) {
                    // Preserve existing urgent decimal orders at the top
                    newOrderNumber = currentOrder;
                } else {
                    // Renumber everything after the urgent prefix as 1, 2, 3, ...
                    newOrderNumber = nextIntegerOrder;
                    nextIntegerOrder += 1;
                }

                // Only send update if the order actually changed
                if (rowId && currentOrder !== newOrderNumber) {
                    // eslint-disable-next-line no-await-in-loop
                    await updateOrderNumber(rowId, newOrderNumber);
                }
            }
        }

        // Reset drag state
        setDraggedIndex(null);
        setDragOverIndex(null);
        setDraggedRow(null);
    }, [draggedRow, rows, calculateTopOrderNumber, updateOrderNumber]);

    const formatDate = (dateValue) => {
        if (!dateValue) return '—';
        try {
            const date = new Date(dateValue);
            if (isNaN(date.getTime())) return '—';
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const year = date.getFullYear();
            return `${month}/${day}/${year}`;
        } catch (e) {
            return '—';
        }
    };

    const formatCellValue = (value) => {
        if (value === null || value === undefined || value === '') {
            return '—';
        }
        if (Array.isArray(value)) {
            return value.join(', ');
        }
        return value;
    };

    const handleGeneratePDF = useCallback(() => {
        generateDraftingWorkLoadPDF(displayRows, columns, lastUpdated);
    }, [displayRows, columns, lastUpdated]);

    const handleFileUpload = async (event) => {
        const file = event.target.files[0];
        if (!file) {
            return;
        }

        await uploadFile(file);

        // Reset file input
        event.target.value = '';
    };

    // Clear upload success message after 3 seconds
    useEffect(() => {
        if (uploadSuccess) {
            const timer = setTimeout(() => {
                clearUploadSuccess();
            }, 3000);
            return () => clearTimeout(timer);
        }
    }, [uploadSuccess, clearUploadSuccess]);


    const formattedLastUpdated = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';

    const hasData = displayRows.length > 0;

    const columnHeaders = useMemo(() => columns, [columns]);

    const tableColumnCount = columnHeaders.length;

    return (
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-8 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-[95%] mx-auto w-full" style={{ width: '100%' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <h1 className="text-3xl font-bold text-white">Drafting Work Load</h1>

                            </div>
                            <div className="flex items-center gap-3">
                                <button
                                    onClick={handleGeneratePDF}
                                    disabled={!hasData || loading}
                                    className={`inline-flex items-center px-4 py-2 rounded-lg font-medium shadow-sm transition-all ${!hasData || loading
                                        ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                        : 'bg-white text-accent-600 hover:bg-accent-50 cursor-pointer'
                                        }`}
                                    title="Generate PDF"
                                >
                                    🖨️ Print/PDF
                                </button>
                                <label className="relative cursor-pointer">
                                    <input
                                        type="file"
                                        accept=".xlsx,.xls"
                                        onChange={handleFileUpload}
                                        disabled={uploading}
                                        className="hidden"
                                        id="file-upload"
                                    />
                                    <span className={`inline-flex items-center px-4 py-2 rounded-lg font-medium shadow-sm transition-all ${uploading
                                        ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                        : 'bg-white text-accent-600 hover:bg-accent-50 cursor-pointer'
                                        }`}>
                                        {uploading ? (
                                            <>
                                                <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-accent-600 mr-2"></span>
                                                Uploading...
                                            </>
                                        ) : (
                                            <>
                                                📤 Upload Excel
                                            </>
                                        )}
                                    </span>
                                </label>
                            </div>
                        </div>
                    </div>

                    <div className="p-6 space-y-4">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-4 border border-gray-200 shadow-sm">
                            <div className="flex flex-col gap-3">
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="flex flex-col gap-3">
                                        <div>
                                            <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                                🎯 Ball In Court
                                            </label>
                                            <div className="grid grid-cols-8 gap-1">
                                                <button
                                                    onClick={() => setSelectedBallInCourt(ALL_OPTION_VALUE)}
                                                    className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedBallInCourt === ALL_OPTION_VALUE
                                                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                        : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                        }`}
                                                    title="All"
                                                >
                                                    All
                                                </button>
                                                {ballInCourtOptions.map((option) => (
                                                    <button
                                                        key={option}
                                                        onClick={() => setSelectedBallInCourt(option)}
                                                        className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedBallInCourt === option
                                                            ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                            : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                            }`}
                                                        title={option}
                                                    >
                                                        {option}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                                👤 Submittal Manager
                                            </label>
                                            <div className="grid grid-cols-8 gap-1">
                                                <button
                                                    onClick={() => setSelectedSubmittalManager(ALL_OPTION_VALUE)}
                                                    className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedSubmittalManager === ALL_OPTION_VALUE
                                                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                        : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                        }`}
                                                    title="All"
                                                >
                                                    All
                                                </button>
                                                {submittalManagerOptions.map((option) => (
                                                    <button
                                                        key={option}
                                                        onClick={() => setSelectedSubmittalManager(option)}
                                                        className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedSubmittalManager === option
                                                            ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                            : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                            }`}
                                                        title={option}
                                                    >
                                                        {option}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                            📁 Project Name
                                        </label>
                                        <div className="grid grid-cols-8 gap-1">
                                            <button
                                                onClick={() => setSelectedProjectName(ALL_OPTION_VALUE)}
                                                className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedProjectName === ALL_OPTION_VALUE
                                                    ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                    : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                    }`}
                                                title="All"
                                            >
                                                All
                                            </button>
                                            {projectNameOptions.map((option) => (
                                                <button
                                                    key={option}
                                                    onClick={() => setSelectedProjectName(option)}
                                                    className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedProjectName === option
                                                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                        : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                        }`}
                                                    title={option}
                                                >
                                                    {option}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 pt-2">
                                    <button
                                        onClick={resetFilters}
                                        className="px-2 py-1 bg-white border border-accent-300 text-accent-700 rounded text-xs font-medium shadow-sm hover:bg-accent-50 transition-all"
                                    >
                                        Reset Filters
                                    </button>
                                    <div className="px-2 py-1 bg-white border border-gray-200 text-gray-600 rounded text-xs font-medium shadow-sm">
                                        Total: <span className="text-gray-900">{displayRows.length}</span> records
                                    </div>
                                    <div className="text-xs text-gray-500 ml-auto">
                                        Last updated: <span className="font-medium text-gray-700">{formattedLastUpdated}</span>
                                    </div>
                                </div>
                            </div>
                            {uploadSuccess && (
                                <div className="mt-4 bg-green-50 border-l-4 border-green-500 text-green-700 px-4 py-3 rounded-lg shadow-sm">
                                    <div className="flex items-start">
                                        <span className="text-xl mr-3">✓</span>
                                        <div>
                                            <p className="font-semibold">File uploaded successfully!</p>
                                            <p className="text-sm mt-1">The data has been refreshed.</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                            {uploadError && (
                                <div className="mt-4 bg-red-50 border-l-4 border-red-500 text-red-700 px-4 py-3 rounded-lg shadow-sm">
                                    <div className="flex items-start">
                                        <span className="text-xl mr-3">⚠️</span>
                                        <div>
                                            <p className="font-semibold">Upload failed</p>
                                            <p className="text-sm mt-1">{uploadError}</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {loading && (
                            <div className="text-center py-12">
                                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                <p className="text-gray-600 font-medium">Loading Drafting Work Load data...</p>
                            </div>
                        )}

                        {fetchError && !loading && (
                            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm">
                                <div className="flex items-start">
                                    <span className="text-xl mr-3">⚠️</span>
                                    <div>
                                        <p className="font-semibold">Unable to load Drafting Work Load data</p>
                                        <p className="text-sm mt-1">{fetchError}</p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {!loading && !fetchError && (
                            <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                                <div className="">
                                    <table className="w-full" style={{ borderCollapse: 'collapse' }}>
                                        <thead className="bg-gray-100">
                                            <tr>
                                                {/* Ellipsis header column - far left */}
                                                <th
                                                    className="px-1 py-0.5 text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300"
                                                    style={{ width: '32px' }}
                                                >
                                                    {/* Empty header for ellipsis column */}
                                                </th>
                                                {columnHeaders.map((column) => {
                                                    const isOrderNumber = column === 'Order Number';
                                                    const isNotes = column === 'Notes';
                                                    const isProjectName = column === 'Project Name';

                                                    if (isProjectName) {
                                                        return (
                                                            <th
                                                                key={column}
                                                                className="px-2 py-0.5 text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300"
                                                            >
                                                                <button
                                                                    onClick={handleProjectNameSortToggle}
                                                                    className="flex items-center justify-center gap-1 hover:bg-gray-200 rounded px-1 py-0.5 transition-colors w-full"
                                                                    title={
                                                                        projectNameSortMode === 'normal' ? 'Click to sort A-Z' :
                                                                            projectNameSortMode === 'a-z' ? 'Click to sort Z-A' :
                                                                                'Click to sort by Order Number'
                                                                    }
                                                                >
                                                                    <span>{column}</span>
                                                                    {projectNameSortMode === 'a-z' && <span className="text-xs">↑</span>}
                                                                    {projectNameSortMode === 'z-a' && <span className="text-xs">↓</span>}
                                                                    {projectNameSortMode === 'normal' && <span className="text-xs text-gray-400">↕</span>}
                                                                </button>
                                                            </th>
                                                        );
                                                    }

                                                    const isStatus = column === 'Status';

                                                    return (
                                                        <th
                                                            key={column}
                                                            className={`${isOrderNumber ? 'px-1 py-0.5 w-16' : 'px-2 py-0.5'} ${isNotes ? 'w-56' : ''} ${isStatus ? 'w-24' : ''} text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300`}
                                                        >
                                                            {column}
                                                        </th>
                                                    );
                                                })}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {!hasData ? (
                                                <tr>
                                                    <td
                                                        colSpan={tableColumnCount + 1}
                                                        className="px-6 py-12 text-center text-gray-500 font-medium bg-white rounded-md"
                                                    >
                                                        No records match the selected filters.
                                                    </td>
                                                </tr>
                                            ) : (
                                                displayRows.map((row, index) => (
                                                    <TableRow
                                                        key={row.id}
                                                        row={row}
                                                        columns={columnHeaders}
                                                        formatCellValue={formatCellValue}
                                                        formatDate={formatDate}
                                                        onOrderNumberChange={updateOrderNumber}
                                                        onNotesChange={updateNotes}
                                                        onStatusChange={updateStatus}
                                                        rowIndex={index}
                                                        onDragStart={handleDragStart}
                                                        onDragOver={handleDragOver}
                                                        onDrop={handleDrop}
                                                        isDragging={draggedIndex}
                                                        dragOverIndex={dragOverIndex}
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
        </div>
    );
}

export default DraftingWorkLoad;

