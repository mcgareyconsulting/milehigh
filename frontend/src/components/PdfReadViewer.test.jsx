import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PdfReadViewer } from './PdfReadViewer.jsx';

describe('PdfReadViewer', () => {
    it('shows empty state when no fileUrl', () => {
        render(<PdfReadViewer fileUrl={null} />);
        expect(screen.getByText(/No drawing selected/i)).toBeInTheDocument();
    });

    it('shows citation bar when citePage is set with a url', () => {
        // Without a real PDF fetch this still mounts the shell; cite bar is independent of load.
        // Stub fetch so the load effect does not explode.
        const orig = global.fetch;
        global.fetch = () => Promise.reject(new Error('no pdf in unit test'));
        try {
            render(
                <PdfReadViewer
                    fileUrl="https://example.test/doc.pdf"
                    citePage={4}
                    citeRuleId="stair-terminal-rise-over-max"
                />
            );
            expect(screen.getByText(/Viewing p4/)).toBeInTheDocument();
            expect(screen.getByText('stair-terminal-rise-over-max')).toBeInTheDocument();
            // The filename now lives on the pane's title switcher, not the canvas.
            expect(screen.getByRole('button', { name: 'Zoom in' })).toBeInTheDocument();
        } finally {
            global.fetch = orig;
        }
    });
});
