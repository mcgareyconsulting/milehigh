import React from 'react';

/**
 * Reusable component for filter button groups
 * @param {string} label - Label for the filter group
 * @param {Array} options - Array of option values to display
 * @param {string} selectedValue - Currently selected value
 * @param {Function} onSelect - Callback when an option is selected
 * @param {string} allOptionValue - Value for "All" option
 * @param {Set} disabledOptions - Set of option values that should be disabled (optional)
 */
export function FilterButtonGroup({ label, options, selectedValue, onSelect, allOptionValue, disabledOptions = null }) {
    const isOptionDisabled = (option) => {
        if (disabledOptions === null) return false;
        return !disabledOptions.has(option);
    };

    return (
        <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                {label}
            </label>
            <div className="grid grid-cols-8 gap-1">
                <button
                    onClick={() => onSelect(allOptionValue)}
                    className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedValue === allOptionValue
                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                        : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                        }`}
                    title="All"
                >
                    All
                </button>
                {options.map((option) => {
                    const isDisabled = isOptionDisabled(option);
                    return (
                        <button
                            key={option}
                            onClick={() => !isDisabled && onSelect(option)}
                            disabled={isDisabled}
                            className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${
                                isDisabled
                                    ? 'bg-gray-100 border border-gray-200 text-gray-400 cursor-not-allowed opacity-50'
                                    : selectedValue === option
                                    ? 'bg-accent-500 text-white hover:bg-accent-600'
                                    : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                            }`}
                            title={option}
                        >
                            {option}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

