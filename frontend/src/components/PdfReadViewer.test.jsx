import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { PdfReadViewer } from './PdfReadViewer.jsx';

// pdf.js needs a worker and a real canvas; neither exists in jsdom. The page column is
// what's under test — that a set renders as one continuous scroll, not a page at a time.
const fakePage = () => ({
    getViewport: () => ({ width: 612, height: 792 }),
    render: () => ({ promise: Promise.resolve() }),
});

vi.mock('pdfjs-dist', () => ({
    GlobalWorkerOptions: {},
    getDocument: () => ({
        promise: Promise.resolve({ numPages: 3, getPage: () => Promise.resolve(fakePage()) }),
    }),
}));
vi.mock('pdfjs-dist/build/pdf.worker.mjs?url', () => ({ default: 'worker.js' }));

const okFetch = () => Promise.resolve({
    ok: true,
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
});

describe('PdfReadViewer', () => {
    it('shows empty state when no fileUrl', () => {
        render(<PdfReadViewer fileUrl={null} />);
        expect(screen.getByText(/No drawing selected/i)).toBeInTheDocument();
    });

    it('shows citation bar when citePage is set with a url', () => {
        // Cite bar is independent of load; stub fetch so the load effect does not explode.
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

    it('stacks every page in one scroll rather than showing one at a time', async () => {
        const orig = global.fetch;
        global.fetch = okFetch;
        try {
            const { container } = render(<PdfReadViewer fileUrl="https://example.test/set.pdf" />);
            await waitFor(() => {
                expect(container.querySelectorAll('[data-page]')).toHaveLength(3);
            });
            // The pill still reports position within the set.
            expect(screen.getByText(/\/ 3/)).toBeInTheDocument();
        } finally {
            global.fetch = orig;
        }
    });

    it('reports the page count to the host', async () => {
        const orig = global.fetch;
        const onNumPages = vi.fn();
        global.fetch = okFetch;
        try {
            render(<PdfReadViewer fileUrl="https://example.test/set.pdf" onNumPages={onNumPages} />);
            await waitFor(() => expect(onNumPages).toHaveBeenCalledWith(3));
        } finally {
            global.fetch = orig;
        }
    });
});
