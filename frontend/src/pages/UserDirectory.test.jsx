import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../utils/auth', () => ({
    checkAuth: vi.fn(),
}));

vi.mock('../services/directoryApi', () => ({
    fetchDirectory: vi.fn(),
}));

import UserDirectory from './UserDirectory.jsx';
import { checkAuth } from '../utils/auth';
import { fetchDirectory } from '../services/directoryApi';

const directory = {
    employees: [
        { id: 1, first_name: 'Colton', last_name: 'Arendt', email: 'carendt@mhmw.com', role: 'Drafter' },
        { id: 2, first_name: 'Bill', last_name: "O'Neill", email: 'boneill@mhmw.com', role: 'Admin, Drafter' },
    ],
    subcontractors: [
        { id: 1, first_name: 'Sam', last_name: 'Sub', email: 'sam@acme.test', role: 'Subcontractor' },
    ],
};

describe('UserDirectory', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('shows an access message and does not fetch when the user is not admin', async () => {
        checkAuth.mockResolvedValue({ is_admin: false });
        render(<UserDirectory />);
        expect(await screen.findByText('Users is available to admins only.')).toBeInTheDocument();
        expect(fetchDirectory).not.toHaveBeenCalled();
    });

    it('lists employees and subcontractors in separate sections', async () => {
        checkAuth.mockResolvedValue({ is_admin: true });
        fetchDirectory.mockResolvedValue(directory);
        render(<UserDirectory />);

        expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument();
        expect(await screen.findByRole('heading', { name: 'Employees' })).toBeInTheDocument();
        expect(screen.getByRole('heading', { name: 'Subcontractors' })).toBeInTheDocument();

        expect(screen.getAllByText('Colton').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Arendt').length).toBeGreaterThan(0);
        expect(screen.getAllByText('carendt@mhmw.com').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Drafter').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Sam').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Sub').length).toBeGreaterThan(0);
        expect(screen.getAllByText('sam@acme.test').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Subcontractor').length).toBeGreaterThan(0);
        expect(screen.queryByRole('button')).not.toBeInTheDocument();

        const tables = document.querySelectorAll('table');
        expect(tables.length).toBe(2);
        tables.forEach((table) => {
            expect(table).toHaveClass('table-fixed');
            expect(table.querySelectorAll('col')).toHaveLength(4);
        });
    });

    it('shows the load error when the directory request fails', async () => {
        checkAuth.mockResolvedValue({ is_admin: true });
        fetchDirectory.mockRejectedValue(new Error('nope'));
        render(<UserDirectory />);
        expect(await screen.findByText('Failed to load users')).toBeInTheDocument();
    });

    it('shows empty states when both lists are empty', async () => {
        checkAuth.mockResolvedValue({ is_admin: true });
        fetchDirectory.mockResolvedValue({ employees: [], subcontractors: [] });
        render(<UserDirectory />);
        await waitFor(() => {
            expect(screen.getByText('No employees yet.')).toBeInTheDocument();
        });
        expect(screen.getByText('No subcontractors yet.')).toBeInTheDocument();
    });
});
