import React, { useState, useEffect } from 'react';

export function JobsTableRow({ row, columns, formatCellValue, formatDate, rowIndex }) {
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

    // Local state for stage (editable but not saved to backend)
    const [localStage, setLocalStage] = useState(row['Stage'] || 'Released');

    // Sync local state when row data changes (e.g., on refresh)
    useEffect(() => {
        setLocalStage(row['Stage'] || 'Released');
    }, [row['Stage']]);

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

                // Truncate Job and Description columns
                const shouldTruncate = column === 'Job' || column === 'Description';
                const maxLength = 10;
                const displayValue = shouldTruncate && rawValue && rawValue.length > maxLength
                    ? rawValue.substring(0, maxLength) + '...'
                    : rawValue;

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
                            <select
                                value={localStage}
                                onChange={(e) => setLocalStage(e.target.value)}
                                className={`w-full px-2 py-0.5 text-[10px] border-2 rounded font-medium focus:outline-none focus:ring-2 focus:ring-offset-1 text-center transition-colors ${currentColorClass}`}
                                style={{ minWidth: '120px' }}
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
                        </td>
                    );
                }

                // For Job and Description, show full value in tooltip, truncated value in cell
                const tooltipValue = shouldTruncate ? rawValue : displayValue;

                return (
                    <td
                        key={`${row.id}-${column}`}
                        className={`${paddingClass} py-0.5 ${whitespaceClass} text-[10px] align-middle font-medium ${rowBgClass} border-r border-gray-300 text-center`}
                        title={tooltipValue}
                    >
                        {displayValue}
                    </td>
                );
            })}
        </tr>
    );
}

