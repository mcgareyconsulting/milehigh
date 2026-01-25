import React, { useState, useEffect } from 'react';

export function StartInstallDateModal({ isOpen, onClose, currentDate, onSave, jobNumber, releaseNumber }) {
    const [dateInput, setDateInput] = useState('');
    const [isHardDate, setIsHardDate] = useState(false);
    const [error, setError] = useState('');

    // Initialize form when modal opens or currentDate changes
    useEffect(() => {
        if (isOpen) {
            // Format current date for display (MM/DD/YYYY)
            if (currentDate) {
                try {
                    const date = new Date(currentDate);
                    if (!isNaN(date.getTime())) {
                        const month = String(date.getMonth() + 1).padStart(2, '0');
                        const day = String(date.getDate()).padStart(2, '0');
                        const year = date.getFullYear();
                        setDateInput(`${month}/${day}/${year}`);
                    } else {
                        setDateInput('');
                    }
                } catch (e) {
                    setDateInput('');
                }
            } else {
                setDateInput('');
            }
            // Default to hard date if there's a current date (likely manual)
            // If no date, default to false (formula-driven)
            setIsHardDate(!!currentDate);
            setError('');
        }
    }, [isOpen, currentDate]);

    const parseDateInput = (input) => {
        // Try to parse MM/DD/YYYY format
        const trimmed = input.trim();
        if (!trimmed) return null;

        // Try MM/DD/YYYY format
        const mmddyyyy = trimmed.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (mmddyyyy) {
            const month = parseInt(mmddyyyy[1], 10);
            const day = parseInt(mmddyyyy[2], 10);
            const year = parseInt(mmddyyyy[3], 10);
            
            if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
                const date = new Date(year, month - 1, day);
                // Check if date is valid (handles invalid dates like Feb 30)
                if (date.getFullYear() === year && 
                    date.getMonth() === month - 1 && 
                    date.getDate() === day) {
                    return date;
                }
            }
        }

        // Try YYYY-MM-DD format (for date picker)
        const yyyymmdd = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (yyyymmdd) {
            const year = parseInt(yyyymmdd[1], 10);
            const month = parseInt(yyyymmdd[2], 10);
            const day = parseInt(yyyymmdd[3], 10);
            
            if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
                const date = new Date(year, month - 1, day);
                if (date.getFullYear() === year && 
                    date.getMonth() === month - 1 && 
                    date.getDate() === day) {
                    return date;
                }
            }
        }

        return null;
    };

    const handleDateInputChange = (e) => {
        const value = e.target.value;
        setDateInput(value);
        setError('');
    };

    const handleSave = () => {
        if (!dateInput.trim() && isHardDate) {
            setError('Please enter a date or uncheck "Hard Date"');
            return;
        }

        const parsedDate = parseDateInput(dateInput);
        
        if (dateInput.trim() && !parsedDate) {
            setError('Invalid date format. Please use MM/DD/YYYY (e.g., 04/07/2026)');
            return;
        }

        // Format date as YYYY-MM-DD for API
        let dateValue = null;
        if (parsedDate) {
            const year = parsedDate.getFullYear();
            const month = String(parsedDate.getMonth() + 1).padStart(2, '0');
            const day = String(parsedDate.getDate()).padStart(2, '0');
            dateValue = `${year}-${month}-${day}`;
        }

        // Only save if it's a hard date, otherwise just close
        if (isHardDate) {
            onSave(dateValue, true);
        } else {
            // Not a hard date, just close without saving
            onClose();
        }
    };

    const handleCancel = () => {
        setDateInput('');
        setIsHardDate(false);
        setError('');
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4">
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-2xl font-bold text-white">
                            Set Start Install Date
                        </h2>
                        <button
                            onClick={handleCancel}
                            className="text-white hover:text-gray-200 text-2xl font-bold"
                        >
                            ×
                        </button>
                    </div>
                    {jobNumber && releaseNumber && (
                        <p className="text-accent-100 text-sm mt-1">
                            Job {jobNumber}-{releaseNumber}
                        </p>
                    )}
                </div>

                <div className="p-6">
                    <div className="mb-4">
                        <label className="block text-sm font-semibold text-gray-700 mb-2">
                            Date (MM/DD/YYYY)
                        </label>
                        <input
                            type="text"
                            value={dateInput}
                            onChange={handleDateInputChange}
                            placeholder="04/07/2026"
                            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 ${
                                error ? 'border-red-500' : 'border-gray-300'
                            }`}
                            maxLength={10}
                        />
                        {error && (
                            <p className="text-red-600 text-sm mt-1">{error}</p>
                        )}
                        <p className="text-gray-500 text-xs mt-1">
                            Enter date in MM/DD/YYYY format (e.g., 04/07/2026)
                        </p>
                    </div>

                    <div className="mb-6">
                        <label className="flex items-center cursor-pointer">
                            <input
                                type="checkbox"
                                checked={isHardDate}
                                onChange={(e) => setIsHardDate(e.target.checked)}
                                className="w-5 h-5 text-accent-600 border-gray-300 rounded focus:ring-accent-500 focus:ring-2"
                            />
                            <span className="ml-3 text-sm font-medium text-gray-700">
                                Hard Date
                            </span>
                        </label>
                        <p className="text-gray-500 text-xs mt-1 ml-8">
                            {isHardDate 
                                ? 'This date will be saved and synced to Trello. Formula calculations will not override it.'
                                : 'Leave unchecked to keep formula-driven dates. Changes will not be saved.'}
                        </p>
                    </div>

                    <div className="flex justify-end gap-3">
                        <button
                            onClick={handleCancel}
                            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-50 transition-all"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleSave}
                            className={`px-4 py-2 rounded-lg font-medium transition-all ${
                                isHardDate
                                    ? 'bg-accent-500 text-white hover:bg-accent-600'
                                    : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                            }`}
                            disabled={!isHardDate}
                        >
                            {isHardDate ? 'Save Hard Date' : 'Save (Hard Date Required)'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

