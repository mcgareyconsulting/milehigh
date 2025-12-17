import React from 'react';

/**
 * Reusable component for filter button groups
 */
export function FilterButtonGroup({ label, options, selectedValue, onSelect, allOptionValue }) {
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
                {options.map((option) => (
                    <button
                        key={option}
                        onClick={() => onSelect(option)}
                        className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedValue === option
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
    );
}

