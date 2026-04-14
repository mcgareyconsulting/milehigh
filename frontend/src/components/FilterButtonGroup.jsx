/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Renders a labeled row of toggle buttons so users can filter table data by a single discrete value.
 * exports:
 *   FilterButtonGroup: Reusable toggle-button group with "All" option and minimized mode
 * imports_from: [react]
 * imported_by: [frontend/src/pages/DraftingWorkLoad.jsx]
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React from 'react';

export function FilterButtonGroup({ label, options, selectedValue, onSelect, allOptionValue, minimized = false }) {
    return (
        <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-slate-200 mb-1.5">
                {label}
            </label>
            {!minimized && (
            <div className="grid grid-cols-8 gap-1">
                <button
                    onClick={() => onSelect(allOptionValue)}
                    className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedValue === allOptionValue
                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                        : 'bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-accent-50 dark:hover:bg-slate-500 hover:border-accent-300'
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
                            : 'bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-accent-50 dark:hover:bg-slate-500 hover:border-accent-300'
                            }`}
                        title={option}
                    >
                        {option}
                    </button>
                ))}
            </div>
            )}
        </div>
    );
}

