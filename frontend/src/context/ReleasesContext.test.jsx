// Unit tests for the pure cursor-merge reducer lifted out of the old
// useJobsDataFetching hook (add/update, soft-delete + archive removal,
// id-sort stability, empty-incoming no-op) plus the provider's login/logout
// re-sync lifecycle.
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { ReleasesProvider, mergeJobs } from './ReleasesContext.jsx';

vi.mock('../services/jobsApi', () => ({
    jobsApi: {
        fetchAllJobs: vi.fn().mockResolvedValue([]),
        fetchData: vi.fn().mockResolvedValue({ jobs: [], latest_timestamp: null }),
    },
}));
import { jobsApi } from '../services/jobsApi';

beforeEach(() => {
    // The reducer logs progress; silence it so test output stays clean.
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.clearAllMocks();
});

const job = (id, extra = {}) => ({ id, 'Job #': id, 'Release #': 'A', ...extra });

describe('mergeJobs', () => {
    it('returns the same array reference when incoming is empty', () => {
        const prev = [job(1), job(2)];
        expect(mergeJobs(prev, [])).toBe(prev);
    });

    it('returns the same array reference when incoming is null/undefined', () => {
        const prev = [job(1)];
        expect(mergeJobs(prev, null)).toBe(prev);
        expect(mergeJobs(prev, undefined)).toBe(prev);
    });

    it('adds a new job', () => {
        const result = mergeJobs([job(1)], [job(2)]);
        expect(result.map(j => j.id)).toEqual([1, 2]);
    });

    it('updates an existing job in place (by id)', () => {
        const result = mergeJobs([job(1, { Stage: 'Cut Start' })], [job(1, { Stage: 'Paint Start' })]);
        expect(result).toHaveLength(1);
        expect(result[0].Stage).toBe('Paint Start');
    });

    it('removes a soft-deleted job (is_active=false)', () => {
        const result = mergeJobs([job(1), job(2)], [job(2, { is_active: false })]);
        expect(result.map(j => j.id)).toEqual([1]);
    });

    it('removes an archived job (is_archived=true)', () => {
        const result = mergeJobs([job(1), job(2)], [job(2, { is_archived: true })]);
        expect(result.map(j => j.id)).toEqual([1]);
    });

    it('ignores a remove for an id not present', () => {
        const prev = [job(1)];
        const result = mergeJobs(prev, [job(99, { is_active: false })]);
        expect(result.map(j => j.id)).toEqual([1]);
    });

    it('sorts the merged result ascending by id', () => {
        const result = mergeJobs([job(3), job(1)], [job(2)]);
        expect(result.map(j => j.id)).toEqual([1, 2, 3]);
    });

    it('handles add + update + remove in one batch', () => {
        const prev = [job(1, { Stage: 'A' }), job(2), job(3)];
        const incoming = [
            job(2, { is_archived: true }),     // remove
            job(1, { Stage: 'B' }),            // update
            job(4),                            // add
        ];
        const result = mergeJobs(prev, incoming);
        expect(result.map(j => j.id)).toEqual([1, 3, 4]);
        expect(result.find(j => j.id === 1).Stage).toBe('B');
    });
});

describe('ReleasesProvider login/logout lifecycle', () => {
    it('does not fetch while disabled', async () => {
        render(<ReleasesProvider enabled={false}><div /></ReleasesProvider>);
        await Promise.resolve();
        expect(jobsApi.fetchAllJobs).not.toHaveBeenCalled();
        expect(jobsApi.fetchData).not.toHaveBeenCalled();
    });

    it('fetches once on enable, including under StrictMode-style re-render', async () => {
        const { rerender } = render(<ReleasesProvider enabled={true}><div /></ReleasesProvider>);
        rerender(<ReleasesProvider enabled={true}><div /></ReleasesProvider>);
        await waitFor(() => expect(jobsApi.fetchAllJobs).toHaveBeenCalledTimes(1));
    });

    it('re-syncs the full dataset on re-login (enabled true→false→true)', async () => {
        const { rerender } = render(<ReleasesProvider enabled={true}><div /></ReleasesProvider>);
        await waitFor(() => expect(jobsApi.fetchAllJobs).toHaveBeenCalledTimes(1));
        // Logout: provider stays mounted (AppShell), enabled drops.
        rerender(<ReleasesProvider enabled={false}><div /></ReleasesProvider>);
        // Re-login must trigger a fresh full sync, not serve the old snapshot.
        rerender(<ReleasesProvider enabled={true}><div /></ReleasesProvider>);
        await waitFor(() => expect(jobsApi.fetchAllJobs).toHaveBeenCalledTimes(2));
    });
});
