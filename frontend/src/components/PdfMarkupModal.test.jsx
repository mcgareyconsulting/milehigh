/**
 * Undo / redo / delete and selection-driven controls in the markup pill, driven through
 * the pdf.js EventBus contract with the viewer itself mocked out. The browser-level
 * behaviour (real strokes, real command stack) was verified by hand against pdf.js
 * 4.10; these pin the wiring: which events enable which buttons, which keys reach the
 * UIManager in Hand mode, and how a selection re-shapes the pill.
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// vi.mock factories are hoisted above every import, so the bus they hand out is hoisted too.
const { buses, FakeEventBus } = vi.hoisted(() => {
    const buses = [];
    class FakeEventBus {
        constructor() { this.listeners = new Map(); buses.push(this); }
        on(name, fn) { (this.listeners.get(name) || this.listeners.set(name, []).get(name)).push(fn); }
        off(name, fn) { this.listeners.set(name, (this.listeners.get(name) || []).filter((f) => f !== fn)); }
        dispatch(name, data) { for (const fn of this.listeners.get(name) || []) fn(data); }
    }
    return { buses, FakeEventBus };
});

const NONE = 0, FREETEXT = 3, INK = 15;
const PARAMS = { FREETEXT_SIZE: 11, FREETEXT_COLOR: 12, INK_COLOR: 21, INK_THICKNESS: 22 };

vi.mock('pdfjs-dist', () => ({
    GlobalWorkerOptions: { workerSrc: 'x' },
    AnnotationEditorType: { NONE: 0, FREETEXT: 3, INK: 15 },
    AnnotationEditorParamsType: { FREETEXT_SIZE: 11, FREETEXT_COLOR: 12, INK_COLOR: 21, INK_THICKNESS: 22 },
    getDocument: () => ({
        promise: Promise.resolve({ numPages: 1, getPage: async () => ({ getAnnotations: async () => [] }), destroy() {} }),
        destroy() {},
    }),
}));
vi.mock('pdfjs-dist/web/pdf_viewer.mjs', () => ({
    EventBus: FakeEventBus,
    PDFLinkService: class { setViewer() {} setDocument() {} },
    PDFViewer: class {
        constructor() { this.pagesCount = 1; this.currentScale = 1; this.annotationEditorMode = { mode: 0 }; }
        setDocument() {}
        getPageView() { return null; }
        scrollPageIntoView() {}
        cleanup() {}
    },
}));
vi.mock('pdfjs-dist/web/pdf_viewer.css', () => ({}));
vi.mock('pdfjs-dist/build/pdf.worker.mjs?url', () => ({ default: 'worker.js' }));

import { PdfMarkupModal } from './PdfMarkupModal';

// The PDF bytes and the version list the editor loads on open.
function stubFetch() {
    vi.stubGlobal('fetch', vi.fn(async (url) => ({
        ok: true,
        status: 200,
        arrayBuffer: async () => new ArrayBuffer(8),
        json: async () => (String(url).endsWith('/drawing/versions')
            ? { versions: [{ id: 1, version_number: 1, source_version_id: null }] }
            : {}),
        text: async () => '',
    })));
}

function makeUiManager(mode = NONE) {
    return {
        mode,
        getMode() { return this.mode; },
        hasSelection: false,
        firstSelectedEditor: null,
        undo: vi.fn(),
        redo: vi.fn(),
        delete: vi.fn(),
        unselectAll: vi.fn(),
        getLayer: () => null,
    };
}

// Renders the hybrid pill, waits for the (mocked) document to load, and hands back the
// bus plus a fake UIManager already announced to the component.
async function mount(mode = NONE) {
    const uiManager = makeUiManager(mode);
    render(
        <PdfMarkupModal isOpen inline variant="hybrid" releaseId={1} versionId={1} mode="edit" onClose={() => {}} />,
    );
    await waitFor(() => expect(buses.length).toBe(1));
    const bus = buses[0];
    act(() => bus.dispatch('annotationeditoruimanager', { uiManager }));
    await waitFor(() => expect(screen.queryByText('Loading drawing…')).toBeNull());
    return { bus, uiManager };
}

// The fake bus calls straight into React listeners, so flush through act() like a real event.
const states = (bus, details) => act(() => bus.dispatch('annotationeditorstateschanged', { details }));
const params = (bus, source, details) => act(() => bus.dispatch('annotationeditorparamschanged', { source, details }));
const undoBtn = () => screen.getByRole('button', { name: /^Undo/ });
const redoBtn = () => screen.getByRole('button', { name: /^Redo/ });
const deleteBtn = () => screen.getByRole('button', { name: /^Delete selected/ });

describe('PdfMarkupModal — undo / redo / delete', () => {
    beforeEach(() => {
        buses.length = 0;
        stubFetch();
    });
    afterEach(() => { vi.unstubAllGlobals(); });

    it('shows the three buttons in the pill, disabled until there is something to act on', async () => {
        await mount();
        expect(undoBtn()).toBeDisabled();
        expect(redoBtn()).toBeDisabled();
        expect(deleteBtn()).toBeDisabled();
    });

    it('follows the pdf.js command stack and drives the UIManager from the buttons', async () => {
        const { bus, uiManager } = await mount();
        states(bus, { hasSomethingToUndo: true, hasSomethingToRedo: false, hasSelectedEditor: false });
        expect(undoBtn()).toBeEnabled();
        expect(redoBtn()).toBeDisabled();
        // The unsaved badge tracks the stack — it is a real change, not a click on a markup.
        expect(screen.getByText('Unsaved markup')).toBeInTheDocument();

        await userEvent.click(undoBtn());
        expect(uiManager.undo).toHaveBeenCalledTimes(1);

        states(bus, { hasSomethingToUndo: false, hasSomethingToRedo: true, hasSelectedEditor: false });
        expect(undoBtn()).toBeDisabled();
        expect(redoBtn()).toBeEnabled();
        expect(screen.queryByText('Unsaved markup')).toBeNull();

        await userEvent.click(redoBtn());
        expect(uiManager.redo).toHaveBeenCalledTimes(1);
    });

    it('selecting a markup merely enables Delete; it does not mark the drawing unsaved', async () => {
        const { bus, uiManager } = await mount();
        uiManager.hasSelection = true;
        states(bus, { hasSomethingToUndo: false, hasSomethingToRedo: false, hasSelectedEditor: true });
        expect(deleteBtn()).toBeEnabled();
        expect(screen.queryByText('Unsaved markup')).toBeNull();

        await userEvent.click(deleteBtn());
        expect(uiManager.delete).toHaveBeenCalledTimes(1);
    });

    it('Ctrl+Z / Ctrl+Y / Delete reach the UIManager in Hand mode, where pdf.js ignores them', async () => {
        const { bus, uiManager } = await mount(NONE);
        states(bus, { hasSomethingToUndo: true, hasSomethingToRedo: true, hasSelectedEditor: true });
        uiManager.hasSelection = true;

        fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
        expect(uiManager.undo).toHaveBeenCalledTimes(1);
        fireEvent.keyDown(window, { key: 'z', ctrlKey: true, shiftKey: true });
        fireEvent.keyDown(window, { key: 'y', ctrlKey: true });
        expect(uiManager.redo).toHaveBeenCalledTimes(2);
        fireEvent.keyDown(window, { key: 'Delete' });
        expect(uiManager.delete).toHaveBeenCalledTimes(1);
        // ⌘Z on a Mac keyboard.
        fireEvent.keyDown(window, { key: 'z', metaKey: true });
        expect(uiManager.undo).toHaveBeenCalledTimes(2);
    });

    it('leaves the keys to pdf.js while a drawing tool is armed, and to the text field while typing', async () => {
        const { bus, uiManager } = await mount(INK);
        states(bus, { hasSomethingToUndo: true, hasSomethingToRedo: true, hasSelectedEditor: true });
        uiManager.hasSelection = true;

        fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
        fireEvent.keyDown(window, { key: 'Delete' });
        expect(uiManager.undo).not.toHaveBeenCalled();
        expect(uiManager.delete).not.toHaveBeenCalled();

        uiManager.mode = NONE;
        const composer = document.createElement('textarea');
        document.body.appendChild(composer);
        fireEvent.keyDown(composer, { key: 'z', ctrlKey: true });
        fireEvent.keyDown(composer, { key: 'Backspace' });
        expect(uiManager.undo).not.toHaveBeenCalled();
        expect(uiManager.delete).not.toHaveBeenCalled();
        composer.remove();
    });

    it('does not fire on an empty stack even if the flags lag', async () => {
        const { uiManager } = await mount(NONE);
        fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
        expect(uiManager.undo).not.toHaveBeenCalled();
    });
});

describe('PdfMarkupModal — selection drives the pill', () => {
    beforeEach(() => {
        buses.length = 0;
        stubFetch();
    });
    afterEach(() => { vi.unstubAllGlobals(); });

    const select = (bus, uiManager, editorType, details) => {
        uiManager.hasSelection = true;
        uiManager.firstSelectedEditor = { editorType };
        states(bus, { hasSelectedEditor: true });
        params(bus, uiManager, details);
    };

    it('swaps between text-size and stroke-width controls as the selection hops, in Hand mode', async () => {
        const { bus, uiManager } = await mount(NONE);
        expect(screen.queryByRole('button', { name: 'Decrease text size' })).toBeNull();
        expect(screen.queryByRole('button', { name: 'Thick stroke width' })).toBeNull();

        select(bus, uiManager, 'freetext', [[PARAMS.FREETEXT_SIZE, 24], [PARAMS.FREETEXT_COLOR, '#2563EB']]);
        expect(screen.getByRole('button', { name: 'Decrease text size' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Thick stroke width' })).toBeNull();
        expect(screen.getByText('24')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Color #2563eb' })).toHaveAttribute('aria-pressed', 'true');

        // Straight hop to a stroke: pdf.js only sends the params event here (the "has a
        // selection" flag never changed), and that alone must re-shape the pill.
        uiManager.firstSelectedEditor = { editorType: 'ink' };
        params(bus, uiManager, [[PARAMS.INK_COLOR, '#dc2626'], [PARAMS.INK_THICKNESS, 12]]);
        expect(screen.queryByRole('button', { name: 'Decrease text size' })).toBeNull();
        expect(screen.getByRole('button', { name: 'Thick stroke width' })).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByRole('button', { name: 'Color #dc2626' })).toHaveAttribute('aria-pressed', 'true');

        // Deselect: back to the defaults (red, Medium, 16), controls follow the (Hand) tool.
        uiManager.hasSelection = false;
        uiManager.firstSelectedEditor = null;
        states(bus, { hasSelectedEditor: false });
        expect(screen.queryByRole('button', { name: 'Thick stroke width' })).toBeNull();
        expect(screen.getByRole('button', { name: 'Color #dc2626' })).toHaveAttribute('aria-pressed', 'true');
    });

    it('a control click restyles the selection through the EventBus and skips no-op clicks', async () => {
        const { bus, uiManager } = await mount(NONE);
        const sent = [];
        bus.on('switchannotationeditorparams', (e) => sent.push([e.type, e.value]));

        select(bus, uiManager, 'ink', [[PARAMS.INK_COLOR, '#dc2626'], [PARAMS.INK_THICKNESS, 6]]);
        await userEvent.click(screen.getByRole('button', { name: 'Medium stroke width' }));   // already Medium
        expect(sent).toEqual([]);

        await userEvent.click(screen.getByRole('button', { name: 'Thin stroke width' }));
        expect(sent).toEqual([[PARAMS.INK_THICKNESS, 2]]);
        expect(screen.getByRole('button', { name: 'Thin stroke width' })).toHaveAttribute('aria-pressed', 'true');

        await userEvent.click(screen.getByRole('button', { name: 'Color #16a34a' }));
        // One palette for every kind: the color goes out for pen/shapes and for text.
        expect(sent.slice(1)).toEqual([[PARAMS.INK_COLOR, '#16a34a'], [PARAMS.FREETEXT_COLOR, '#16a34a']]);
        expect(screen.getByRole('button', { name: 'Color #16a34a' })).toHaveAttribute('aria-pressed', 'true');
    });

    it('A− / A+ resize a selected text box from Hand mode', async () => {
        const { bus, uiManager } = await mount(NONE);
        const sent = [];
        bus.on('switchannotationeditorparams', (e) => sent.push([e.type, e.value]));
        select(bus, uiManager, 'freetext', [[PARAMS.FREETEXT_SIZE, 20], [PARAMS.FREETEXT_COLOR, '#111827']]);
        await userEvent.click(screen.getByRole('button', { name: 'Increase text size' }));
        expect(sent).toEqual([[PARAMS.FREETEXT_SIZE, 22]]);
        expect(screen.getByText('22')).toBeInTheDocument();
    });
});
