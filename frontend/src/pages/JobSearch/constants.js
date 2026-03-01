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
