/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared labor/materials/equipment line-item editing UI for T&M tickets — extracted
 *          out of TMTicketFormModal.jsx so the subcontractor-facing ticket page can reuse the
 *          exact same field-agnostic, mobile-responsive components instead of forking them.
 * exports:
 *   LineItemTable: Full section (title, +Add row, mobile cards below sm:, table at sm:+).
 *   LineItemCards: Just the mobile card list (used internally by LineItemTable and available
 *                  standalone if a caller ever needs the card view without the table half).
 * imports_from: [react]
 * imported_by: [components/TMTicketFormModal.jsx, pages/SubcontractorTicketDetail.jsx]
 * invariants:
 *   - Field-agnostic: columns/rows/onChange contract, no knowledge of labor vs materials vs
 *     equipment — callers supply the column config.
 *   - Components only in this file (non-component constants live in tmFieldHelpers.js) —
 *     required by the react-refresh/only-export-components lint rule.
 */

// Below sm: (640px — covers ~375-430px portrait phones like the iPhone SE/e-tier), a
// horizontally-scrolling table of 5-7 columns nested inside an already-scrolling modal is
// unusable on a touchscreen: ambiguous scroll direction, controls scrolled out of reach.
// So under sm: each row renders as a stacked card instead; the table returns at sm:+ where
// there's room for it. Both share the same columns/rows/onChange contract.
export function LineItemCards({ columns, rows, onChange, onRemove }) {
    if (rows.length === 0) {
        return (
            <div className="rounded-lg border border-dashed border-gray-200 dark:border-slate-700 px-3 py-3 text-center text-xs text-gray-400 dark:text-slate-500">
                No rows
            </div>
        );
    }
    return (
        <div className="space-y-2">
            {rows.map((row, idx) => (
                <div key={idx} className="rounded-lg border border-gray-200 dark:border-slate-700 p-3 bg-gray-50/50 dark:bg-slate-900/30">
                    <div className="grid grid-cols-2 gap-2">
                        {columns.map(c => (
                            <div key={c.key} className={c.wide ? 'col-span-2' : ''}>
                                <label className="block text-[11px] font-medium text-gray-500 dark:text-slate-400 mb-0.5">{c.label}</label>
                                <input
                                    type={c.numeric ? 'number' : 'text'}
                                    value={row[c.key] ?? ''}
                                    onChange={e => onChange(idx, { [c.key]: e.target.value })}
                                    className="w-full px-2.5 py-2.5 text-sm rounded-md border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100"
                                />
                            </div>
                        ))}
                    </div>
                    <button type="button" onClick={() => onRemove(idx)}
                        className="mt-2 w-full min-h-[40px] text-xs font-medium rounded-md border border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20">
                        Remove row
                    </button>
                </div>
            ))}
        </div>
    );
}

export function LineItemTable({ title, readOnly, columns, rows, onChange, onAdd, onRemove }) {
    return (
        <div>
            <div className="flex items-center justify-between mb-1">
                <h4 className="text-xs font-semibold text-gray-600 dark:text-slate-300">{title}</h4>
                {!readOnly && (
                    <button type="button" onClick={onAdd}
                        className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">
                        + Add row
                    </button>
                )}
            </div>

            {readOnly ? null : (
                <div className="sm:hidden">
                    <LineItemCards columns={columns} rows={rows} onChange={onChange} onRemove={onRemove} />
                </div>
            )}
            {readOnly && rows.length === 0 && (
                <div className="sm:hidden rounded-lg border border-dashed border-gray-200 dark:border-slate-700 px-3 py-3 text-center text-xs text-gray-400 dark:text-slate-500">
                    No rows
                </div>
            )}
            {readOnly && rows.length > 0 && (
                <div className="sm:hidden space-y-2">
                    {rows.map((row, idx) => (
                        <div key={idx} className="rounded-lg border border-gray-200 dark:border-slate-700 p-3 bg-gray-50/50 dark:bg-slate-900/30">
                            <div className="grid grid-cols-2 gap-2">
                                {columns.map(c => (
                                    <div key={c.key} className={c.wide ? 'col-span-2' : ''}>
                                        <span className="block text-[11px] font-medium text-gray-500 dark:text-slate-400 mb-0.5">{c.label}</span>
                                        <span className="block text-sm text-gray-900 dark:text-slate-100 truncate">{row[c.key] || '—'}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <div className="hidden sm:block overflow-x-auto rounded-lg border border-gray-200 dark:border-slate-700">
                <table className="min-w-full text-xs">
                    <thead className="bg-gray-50 dark:bg-slate-900/40">
                        <tr>
                            {columns.map(c => (
                                <th key={c.key} className="px-2 py-1.5 text-left font-medium text-gray-500 dark:text-slate-400 whitespace-nowrap">{c.label}</th>
                            ))}
                            {!readOnly && <th className="px-2 py-1.5" />}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.length === 0 ? (
                            <tr>
                                <td colSpan={columns.length + (readOnly ? 0 : 1)} className="px-2 py-2 text-center text-gray-400 dark:text-slate-500">
                                    No rows
                                </td>
                            </tr>
                        ) : rows.map((row, idx) => (
                            <tr key={idx} className="border-t border-gray-100 dark:border-slate-800">
                                {columns.map(c => (
                                    <td key={c.key} className="px-1 py-1">
                                        <input
                                            type={c.numeric ? 'number' : 'text'}
                                            value={row[c.key] ?? ''}
                                            disabled={readOnly}
                                            onChange={e => onChange(idx, { [c.key]: e.target.value })}
                                            className="w-full min-w-[70px] px-1.5 py-1 text-xs rounded border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 disabled:opacity-70"
                                        />
                                    </td>
                                ))}
                                {!readOnly && (
                                    <td className="px-1 py-1">
                                        <button type="button" onClick={() => onRemove(idx)} title="Remove row"
                                            className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 text-xs px-1">✕</button>
                                    </td>
                                )}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
