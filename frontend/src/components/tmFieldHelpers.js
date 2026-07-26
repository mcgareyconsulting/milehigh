/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared non-component constants for T&M line-item forms — blank-row factories and
 *          field styling. Split out of tmLineItems.jsx (which holds only components) because
 *          React Fast Refresh can't reliably hot-reload a file that mixes component and
 *          non-component exports (enforced by the react-refresh/only-export-components lint rule).
 * exports:
 *   emptyLabor, emptyMaterial, emptyEquipment: Blank-row factories for the three line-item shapes.
 *   inputClass, labelClass: Shared field styling, reused across every T&M form surface.
 * imported_by: [components/TMTicketFormModal.jsx, pages/SubcontractorTicketDetail.jsx]
 */
export const emptyLabor = () => ({ name: '', company: '', classification: '', hours_reg: '', hours_ot: '', hours_dt: '', notes: '' });
export const emptyMaterial = () => ({ description: '', quantity: '', unit: '', length: '', notes: '' });
export const emptyEquipment = () => ({ description: '', quantity: '', hours: '', operator: '', notes: '' });

export const inputClass = 'w-full px-3 py-2.5 sm:py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 disabled:opacity-70';
export const labelClass = 'block text-xs font-medium text-gray-600 dark:text-slate-300 mb-1';
