/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Single source of truth for the installer-crew lane/column palette, so a team gets the same color in the PM Board list view and the Gantt timeline. Indexed by the team's position in the /brain/installer-teams roster. Also mirrored server-side by the deprecated /gantt-data route (routes.py).
 * exports:
 *   INSTALLER_PALETTE: 12 hex colors cycled by roster index
 * imports_from: []
 * imported_by: [../components/PMBoardList.jsx, ../components/GanttChart.jsx]
 */
export const INSTALLER_PALETTE = [
    '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899',
    '#06B6D4', '#F97316', '#84CC16', '#6366F1', '#14B8A6', '#F43F5E',
];
