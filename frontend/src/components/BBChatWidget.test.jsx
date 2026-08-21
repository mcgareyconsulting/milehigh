import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import BBChatWidget, { CarmenButton } from './BBChatWidget.jsx';

describe('CarmenButton', () => {
    it('is a circular CM launcher', () => {
        render(<CarmenButton onClick={() => {}} />);
        const btn = screen.getByRole('button', { name: 'Open Carmen chat' });
        expect(btn).toHaveAttribute('data-carmen', 'launcher');
        expect(btn).toHaveClass('rounded-full');
        expect(btn.textContent).toBe('CM');
    });

    it('toggles the expanded label when open', () => {
        render(<CarmenButton onClick={() => {}} open />);
        expect(screen.getByRole('button', { name: 'Close Carmen chat' })).toHaveAttribute('aria-expanded', 'true');
    });
});

describe('BBChatWidget', () => {
    beforeEach(() => {
        window.innerWidth = 1024;
        window.innerHeight = 768;
    });

    it('renders nothing when disabled', () => {
        render(<BBChatWidget enabled={false} isAdmin={false} open onClose={() => {}} />);
        expect(screen.queryByRole('dialog', { name: 'Carmen chat' })).not.toBeInTheDocument();
    });

    it('renders nothing when closed — no floating corner bubble', () => {
        render(<BBChatWidget enabled isAdmin={false} open={false} onClose={() => {}} />);
        expect(screen.queryByRole('dialog', { name: 'Carmen chat' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Open Carmen chat' })).not.toBeInTheDocument();
        expect(document.querySelector('[data-carmen="bubble"]')).toBeNull();
    });

    it('opens an expandable panel anchored to the upper-right bubble', () => {
        render(<BBChatWidget enabled isAdmin={false} open onClose={() => {}} />);
        const panel = screen.getByRole('dialog', { name: 'Carmen chat' });
        expect(panel).toHaveAttribute('data-carmen', 'panel');
        expect(panel.style.right).not.toBe('');
        expect(panel.style.top).not.toBe('');
        expect(panel.style.left).toBe('');
        expect(screen.getByRole('separator', { name: 'Resize Carmen chat' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Close Carmen chat' })).toBeInTheDocument();
    });

    it('closes from the header and from an outside click', () => {
        const onClose = vi.fn();
        render(<BBChatWidget enabled isAdmin={false} open onClose={onClose} />);
        fireEvent.click(screen.getByRole('button', { name: 'Close Carmen chat' }));
        expect(onClose).toHaveBeenCalledTimes(1);

        onClose.mockClear();
        fireEvent.mouseDown(document.body);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('expands height when the bottom handle is dragged down', () => {
        render(<BBChatWidget enabled isAdmin={false} open onClose={() => {}} />);
        const panel = document.querySelector('[data-carmen="panel"]');
        const grip = screen.getByRole('separator', { name: 'Resize Carmen chat' });
        const startH = parseFloat(panel.style.height) || 420;

        fireEvent.mouseDown(grip, { clientX: 500, clientY: 400, button: 0 });
        fireEvent.mouseMove(document.body, { clientX: 500, clientY: 520, buttons: 1 });
        fireEvent.mouseUp(document.body);

        expect(parseFloat(panel.style.height)).toBeGreaterThan(startH);
    });

    it('double-clicking the height handle fills the remaining viewport', () => {
        render(<BBChatWidget enabled isAdmin={false} open onClose={() => {}} />);
        const panel = document.querySelector('[data-carmen="panel"]');
        const grip = screen.getByRole('separator', { name: 'Resize Carmen chat' });
        const startH = parseFloat(panel.style.height) || 420;

        fireEvent.doubleClick(grip);
        expect(parseFloat(panel.style.height)).toBeGreaterThan(startH);
    });
});
