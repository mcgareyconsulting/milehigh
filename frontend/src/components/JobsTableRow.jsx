import React, { useState, useEffect } from 'react';
import { jobsApi } from '../services/jobsApi';

export function JobsTableRow({ row, columns, formatCellValue, formatDate, rowIndex, onStageUpdateError, onStageUpdateSuccess }) {
    // Alternate row background colors with higher contrast
    const rowBgClass = rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-200';

    // Stage options with simplified names for display
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Cut start', label: 'Cut start' },
        { value: 'Fit Up Complete.', label: 'Fitup comp' },
        { value: 'Paint complete', label: 'Paint comp' },
        { value: 'Store at MHMW for shipping', label: 'Store' },
        { value: 'Shipping planning', label: 'Ship plan' },
        { value: 'Shipping completed', label: 'Ship comp' }
    ];

    // Color mapping for each stage (using full value names)
    const stageColors = {
        'Released': 'bg-blue-100 text-blue-800 border-blue-300',
        'Cut start': 'bg-purple-100 text-purple-800 border-purple-300',
        'Fit Up Complete.': 'bg-green-100 text-green-800 border-green-300',
        'Paint complete': 'bg-yellow-100 text-yellow-800 border-yellow-300',
        'Store at MHMW for shipping': 'bg-orange-100 text-orange-800 border-orange-300',
        'Shipping planning': 'bg-indigo-100 text-indigo-800 border-indigo-300',
        'Shipping completed': 'bg-gray-100 text-gray-800 border-gray-300'
    };

    // Local state for stage
    const [localStage, setLocalStage] = useState(row['Stage'] || 'Released');
    const [isUpdating, setIsUpdating] = useState(false);
    const [error, setError] = useState(null);

    // Sync local state when row data changes (e.g., on refresh)
    useEffect(() => {
        setLocalStage(row['Stage'] || 'Released');
        setError(null); // Clear error on data refresh
    }, [row['Stage']]);

    const handleStageChange = async (newStage) => {
        // Optimistically update UI
        const previousStage = localStage;
        setLocalStage(newStage);
        setError(null);
        setIsUpdating(true);

        try {
            // Skip "Cut start" - do nothing (backend also handles this, but we can skip the API call)
            if (newStage === 'Cut start') {
                setIsUpdating(false);
                return;
            }

            const job = row['Job #'];
            const release = row['Release #'];

            await jobsApi.updateStage(job, release, newStage);
            setIsUpdating(false);

            // Notify parent to refetch data after successful update
            if (onStageUpdateSuccess) {
                onStageUpdateSuccess();
            }
        } catch (err) {
            // Rollback on error
            setLocalStage(previousStage);
            setError(err.message || 'Failed to update stage');
            setIsUpdating(false);

            // Notify parent component if callback provided
            if (onStageUpdateError) {
                onStageUpdateError(row, err);
            }
        }
    };

    return (
        <tr
            className={`${rowBgClass} hover:bg-gray-100 transition-colors duration-150 border-b border-gray-300`}
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
                    const currentColorClass = stageColors[localStage] || stageColors['Released'];
                    // Get display label for current stage
                    const currentOption = stageOptions.find(opt => opt.value === localStage);
                    const currentLabel = currentOption ? currentOption.label : localStage;

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`${paddingClass} py-0.5 whitespace-nowrap text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 text-center`}
                            style={{ minWidth: '140px' }}
                        >
                            <div className="relative">
                                <select
                                    value={localStage}
                                    onChange={(e) => handleStageChange(e.target.value)}
                                    disabled={isUpdating}
                                    className={`w-full px-2 py-0.5 text-[10px] border-2 rounded font-medium focus:outline-none focus:ring-2 focus:ring-offset-1 text-center transition-colors ${currentColorClass} ${isUpdating ? 'opacity-50 cursor-not-allowed' : ''} ${error ? 'border-red-500' : ''}`}
                                    style={{ minWidth: '120px' }}
                                    title={error || (isUpdating ? 'Updating...' : '')}
                                >
                                    {stageOptions.map((option) => {
                                        const optionColorClass = stageColors[option.value] || stageColors['Released'];
                                        return (
                                            <option
                                                key={option.value}
                                                value={option.value}
                                                className={optionColorClass}
                                            >
                                                {option.label}
                                            </option>
                                        );
                                    })}
                                </select>
                                {isUpdating && (
                                    <div className="absolute inset-0 flex items-center justify-center bg-white bg-opacity-50">
                                        <div className="w-3 h-3 border-2 border-accent-500 border-t-transparent rounded-full animate-spin"></div>
                                    </div>
                                )}
                            </div>
                            {error && (
                                <div className="text-[8px] text-red-600 mt-0.5" title={error}>
                                    Error: {error}
                                </div>
                            )}
                        </td>
                    );
                }

                // For Job and Description, show full value in tooltip
                const tooltipValue = shouldWrapAndTruncate ? rawValue : rawValue;

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
    );
}

