import { useState, useEffect } from 'react';

/** Highlight duration in ms when navigating from Job Search Jump To */
export const JUMP_TO_HIGHLIGHT_MS = 3500;

/** Offset from top of table scroll area so row appears below sticky header (px) */
const TABLE_STICKY_HEADER_OFFSET = 44;

/** Selectors for table scroll containers (Job Log, Drafting Work Load, etc.) — scroll only the container, not the page */
const TABLE_SCROLL_CONTAINER_SELECTORS = '.job-log-table-scroll-hide-scrollbar, .dwl-table-scroll-hide-scrollbar';

/**
 * Scroll a row into view inside a table scroll container only (no page scroll).
 * Keeps title and nav visible. Uses container.scrollTo so the document does not scroll.
 */
function scrollRowInContainerIntoView(el) {
  const container = el.closest(TABLE_SCROLL_CONTAINER_SELECTORS);
  if (!container) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }

  // Ensure the container is actually scrollable
  if (container.scrollHeight <= container.clientHeight) {
    // Container is not scrollable, row is already visible
    return;
  }

  const rowRect = el.getBoundingClientRect();
  const containerRect = container.getBoundingClientRect();
  const rowRelativeTop = rowRect.top - containerRect.top + container.scrollTop;
  const desiredScrollTop = rowRelativeTop - TABLE_STICKY_HEADER_OFFSET;
  container.scrollTo({ top: Math.max(0, desiredScrollTop), behavior: 'smooth' });
}

/**
 * Handles scroll-to-row and yellow highlight when navigating from Job Search "Jump To".
 * Reads URL params, scrolls to the matching row, and applies a temporary highlight.
 * On Job Log and Drafting Work Load, scrolls only the table container so the page title and nav stay visible.
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
          scrollRowInContainerIntoView(el);
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
          try {
            scrollRowInContainerIntoView(el);
          } catch (error) {
            console.warn('Jump-to scroll failed:', error);
          }
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
