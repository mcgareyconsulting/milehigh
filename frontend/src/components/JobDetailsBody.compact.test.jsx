/**
 * JobDetailsBody `compact` — the Splices tab's side panel. It shows Schedule, Details and the
 * active to-dos only, and never loads the photos or material orders it leaves out. Without
 * `compact` the Details tab is unchanged.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const api = vi.hoisted(() => ({
    getMaterialOrders: vi.fn(),
    getReleasePhotos: vi.fn(),
    getReleaseChecklist: vi.fn(),
    getInstallerTeams: vi.fn(),
}));
vi.mock('../services/jobsApi', () => ({ jobsApi: api }));
vi.mock('../utils/auth', () => ({ checkAuth: vi.fn(() => Promise.resolve({ is_admin: false })) }));

import { JobDetailsBody } from './JobDetailsBody';

const job = {
    id: 3, 'Job #': 555, 'Release #': '551.2', Stage: 'Weld Start', installer: 'Saul 1',
    'Install HRS': 14, parent_release_id: 1,
};

beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.getMaterialOrders.mockResolvedValue({ orders: [] });
    api.getReleasePhotos.mockResolvedValue([]);
    api.getReleaseChecklist.mockResolvedValue({
        todos: [{ id: 7, title: 'Confirm rail count with GC', status: 'Open', item_type: 'Action' }],
    });
    api.getInstallerTeams.mockResolvedValue([]);
});

describe('JobDetailsBody compact', () => {
    it('shows schedule, details and to-dos, and skips photos + materials entirely', async () => {
        render(<JobDetailsBody job={job} releaseId={3} compact />);
        expect(await screen.findByText('Confirm rail count with GC')).toBeInTheDocument();
        expect(screen.getByText('Schedule')).toBeInTheDocument();
        expect(screen.getByText('Details')).toBeInTheDocument();
        expect(screen.getByText('Active to-dos')).toBeInTheDocument();
        expect(screen.queryByText(/^Photos/)).toBeNull();
        expect(screen.queryByText('Materials ordered')).toBeNull();
        expect(api.getReleaseChecklist).toHaveBeenCalledWith(3);
        expect(api.getReleasePhotos).not.toHaveBeenCalled();
        expect(api.getMaterialOrders).not.toHaveBeenCalled();
    });

    it('the full Details tab still loads and shows photos + materials', async () => {
        render(<JobDetailsBody job={job} releaseId={3} />);
        await waitFor(() => expect(api.getReleasePhotos).toHaveBeenCalledWith(3));
        expect(api.getMaterialOrders).toHaveBeenCalled();
        expect(screen.getByText(/^Photos/)).toBeInTheDocument();
        expect(screen.getByText('Materials ordered')).toBeInTheDocument();
    });
});
