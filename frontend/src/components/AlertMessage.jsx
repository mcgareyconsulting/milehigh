import React from 'react';

/**
 * Reusable alert message component
 */
export function AlertMessage({ type, title, message, icon }) {
    const styles = {
        success: {
            container: 'bg-green-50 dark:bg-green-900/30 border-l-4 border-green-500 text-green-700 dark:text-green-200',
            icon: '✓',
        },
        error: {
            container: 'bg-red-50 dark:bg-red-900/30 border-l-4 border-red-500 text-red-700 dark:text-red-200',
            icon: '⚠️',
        },
    };

    const style = styles[type] || styles.error;
    const displayIcon = icon || style.icon;

    return (
        <div className={`mt-4 ${style.container} px-4 py-3 rounded-lg shadow-sm`}>
            <div className="flex items-start">
                <span className="text-xl mr-3">{displayIcon}</span>
                <div>
                    <p className="font-semibold">{title}</p>
                    {message && <p className="text-sm mt-1">{message}</p>}
                </div>
            </div>
        </div>
    );
}

