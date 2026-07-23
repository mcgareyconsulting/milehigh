// The drill-through modal's dismissal rules, which are the easy ones to get subtly wrong:
// the backdrop closes but the panel inside it must not, and Escape closes from anywhere.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { PanelModal, ModalSection, ModalRow } from './PanelModal.jsx';

afterEach(cleanup);

function open(onClose = vi.fn()) {
  render(
    <PanelModal open title="📋 Submittals — Full Detail" onClose={onClose}>
      <ModalSection title="Status">
        <ModalRow label="Structural Steel">Approved</ModalRow>
      </ModalSection>
    </PanelModal>,
  );
  return onClose;
}

describe('PanelModal', () => {
  it('renders nothing when closed', () => {
    render(<PanelModal open={false} title="Hidden" onClose={vi.fn()}><p>body</p></PanelModal>);
    // Not merely hidden — an open-but-invisible dialog would stay in the a11y tree.
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByText('body')).toBeNull();
  });

  it('renders the title and section content when open', () => {
    open();
    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByText('📋 Submittals — Full Detail')).toBeDefined();
    expect(screen.getByText('Structural Steel')).toBeDefined();
    expect(screen.getByText('Approved')).toBeDefined();
  });

  it('closes on the ✕ button', () => {
    const onClose = open();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape', () => {
    const onClose = open();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on a backdrop click but not on a click inside the dialog', () => {
    const onClose = open();

    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled(); // clicks bubble to the backdrop — target guards it

    fireEvent.click(screen.getByRole('presentation'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('restores page scrolling when it unmounts', () => {
    const { unmount } = render(
      <PanelModal open title="T" onClose={vi.fn()}><p>body</p></PanelModal>,
    );
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(document.body.style.overflow).not.toBe('hidden');
  });
});
