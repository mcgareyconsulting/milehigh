/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Reusable data table for JobSearch results that optionally renders a jump-to action column linking rows to their detail pages.
 * exports:
 *   JobSearchTable: Table component accepting column definitions, row data, and an optional jumpTo URL builder
 * imports_from: [react, react-router-dom, ../../utils/formatters]
 * imported_by: [pages/JobSearch/index.jsx, components/QuickSearch.jsx]
 * invariants:
 *   - When jumpTo prop is provided, an extra action column is appended with navigation buttons
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { formatCellValue } from '../../utils/formatters';

export function JobSearchTable({ columns, rows, emptyMessage, jumpTo }) {
  const navigate = useNavigate();
  const allColumns = jumpTo
    ? [...columns, { key: '_jump', label: 'Jump To', isAction: true }]
    : columns;

  return (
    <div className="flex flex-col min-h-0 border border-hairline rounded-xl bg-surface shadow-sm overflow-hidden">
      <div className="overflow-x-auto flex-1 min-h-0">
        <table className="w-full text-sm">
          <thead className="bg-head-bg text-left text-ink-2 font-semibold sticky top-0 shadow-sm">
            <tr>
              {allColumns.map(({ key, label }) => (
                <th key={key} className="px-4 py-3 text-left whitespace-nowrap">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={allColumns.length} className="px-4 py-8 text-center text-ink-3">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              rows.map((row, idx) => (
                <tr key={idx} className="hover:bg-surface-2">
                  {allColumns.map((col) => {
                    if (col.isAction && jumpTo) {
                      const url = jumpTo.getUrl(row);
                      return (
                        <td key={col.key} className="px-4 py-2 whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => { if (url) { navigate(url); jumpTo.onJump?.(); } }}
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
                      <td key={key} className={`px-4 py-2 whitespace-nowrap text-ink ${className}`}>
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
