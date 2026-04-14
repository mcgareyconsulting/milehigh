/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared column definitions, validation helpers, and URL builders for the JobSearch feature so table config stays DRY.
 * exports:
 *   RELEASES_COLS: Column config array for the releases results table
 *   SUBMITTALS_COLS: Column config array for the submittals results table
 *   isValidJobInput: Validates that input is exactly 3 digits
 *   getReleaseJumpUrl: Builds a /job-log deep-link for a release row
 *   getSubmittalJumpUrl: Builds a /drafting-work-load deep-link for a submittal row
 * imports_from: [../../utils/formatters]
 * imported_by: [pages/JobSearch/index.jsx]
 * invariants:
 *   - Job input must be exactly 3 digits (e.g. 001, 400)
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { formatDateShort, formatCellValue } from '../../utils/formatters';

export const RELEASES_COLS = [
  { key: 'job_release', label: 'Job-Release', className: 'font-mono' },
  { key: 'job_name', label: 'Job Name' },
  { key: 'stage', label: 'Stage' },
  { key: 'start_install', label: 'Start Install', format: (v) => formatDateShort(v) },
];

export const SUBMITTALS_COLS = [
  { key: 'title', label: 'Title' },
  { key: 'status', label: 'Status' },
  { key: 'ball_in_court', label: 'BIC' },
  { key: 'submittal_drafting_status', label: 'Drafting Status' },
  { key: 'due_date', label: 'Due Date', format: (v) => formatDateShort(v) },
  {
    key: 'days_since_ball_in_court_update',
    label: 'Time Since Last BIC',
    format: (v) => (v != null ? `${v} days` : '—'),
  },
];

const JOB_INPUT_REGEX = /^\d{3}$/;

export function isValidJobInput(value) {
  const trimmed = value?.trim() ?? '';
  return trimmed.length === 3 && JOB_INPUT_REGEX.test(trimmed);
}

export function getReleaseJumpUrl(row) {
  const job = row.job ?? row.job_release?.split?.('-')[0];
  const release = row.release ?? row.job_release?.split?.('-').slice(1).join('-');
  if (job == null || release == null || String(job) === '' || String(release) === '') {
    return null;
  }
  return `/job-log?job=${job}&release=${encodeURIComponent(release)}`;
}

export function getSubmittalJumpUrl(row) {
  const sid = row.submittal_id;
  if (sid == null || sid === '') return null;
  return `/drafting-work-load?highlight=${encodeURIComponent(String(sid))}`;
}
