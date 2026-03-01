import React from 'react';
import { useNavigate } from 'react-router-dom';
import { formatCellValue } from '../../utils/formatters';

export function JobSearchTable({ columns, rows, emptyMessage, jumpTo }) {
  const navigate = useNavigate();
  const allColumns = jumpTo
    ? [...columns, { key: '_jump', label: 'Jump To', isAction: true }]
    : columns;

  return (
    <div className="flex flex-col min-h-0 border border-gray-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-800 shadow-sm overflow-hidden">
      <div className="overflow-x-auto flex-1 min-h-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-100 dark:bg-slate-700 text-left text-gray-700 dark:text-slate-200 font-semibold sticky top-0 shadow-sm">
            <tr>
              {allColumns.map(({ key, label }) => (
                <th key={key} className="px-4 py-3 text-left whitespace-nowrap">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-slate-600">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={allColumns.length} className="px-4 py-8 text-center text-gray-500 dark:text-slate-400">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              rows.map((row, idx) => (
                <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-slate-700/50">
                  {allColumns.map((col) => {
                    if (col.isAction && jumpTo) {
                      const url = jumpTo.getUrl(row);
                      return (
                        <td key={col.key} className="px-4 py-2 whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => url && navigate(url)}
                            disabled={!url}
                            className="px-2 py-1 text-xs font-medium bg-accent-500 text-white rounded hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            Jump To
                          </button>
                        </td>
                      );
                    }
                    const { key, format, className = '' } = col;
                    const val = row[key];
                    const display = format ? format(val) : formatCellValue(val);
                    return (
                      <td key={key} className={`px-4 py-2 whitespace-nowrap text-gray-900 dark:text-slate-100 ${className}`}>
                        {display}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
