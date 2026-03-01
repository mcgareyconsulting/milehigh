import { useState, useEffect } from 'react';

/** Highlight duration in ms when navigating from Job Search Jump To */
export const JUMP_TO_HIGHLIGHT_MS = 3500;

/**
 * Handles scroll-to-row and yellow highlight when navigating from Job Search "Jump To".
 * Reads URL params, scrolls to the matching row, and applies a temporary highlight.
 *
 * @param {Object} options
 * @param {boolean} options.loading - Whether page data is still loading
 * @param {Object} options.searchParams - URL search params (from useSearchParams())
 * @param {'job-release' | 'submittal'} options.mode - 'job-release' for job+release, 'submittal' for highlight param
 * @param {number} options.durationMs - How long to show the highlight
 */
export function useJumpToHighlight({ loading, searchParams, mode, durationMs = JUMP_TO_HIGHLIGHT_MS }) {
  const [jumpToTarget, setJumpToTarget] = useState(null);

  useEffect(() => {
    if (loading) return;

    if (mode === 'job-release') {
      const job = searchParams.get('job');
      const release = searchParams.get('release');
      if (!job || release == null) return;

      const timer = setTimeout(() => {
        const el = document.querySelector(
          `tr[data-job="${String(job)}"][data-release="${String(release)}"]`
        );
        if (el) {
          el.classList.add('jump-to-scroll-target');
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          setJumpToTarget({ job: String(job), release: String(release) });
          setTimeout(() => {
            el.classList.remove('jump-to-scroll-target');
            setJumpToTarget(null);
          }, durationMs);
        }
      }, 300);

      return () => clearTimeout(timer);
    }

    if (mode === 'submittal') {
      const highlight = searchParams.get('highlight');
      if (!highlight) return;

      const timer = setTimeout(() => {
        const el = document.querySelector(
          `tr[data-submittal-id="${CSS.escape(String(highlight))}"]`
        );
        if (el) {
          el.classList.add('jump-to-scroll-target');
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          setJumpToTarget(String(highlight));
          setTimeout(() => {
            el.classList.remove('jump-to-scroll-target');
            setJumpToTarget(null);
          }, durationMs);
        }
      }, 300);

      return () => clearTimeout(timer);
    }
  }, [loading, searchParams, mode, durationMs]);

  return jumpToTarget;
}
