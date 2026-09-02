import { describe, it, expect } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import { usePersistScroll } from './usePersistScroll';

function Probe({ storeRef }) {
    const persist = usePersistScroll(storeRef);
    return (
        <div data-testid="scroller" ref={persist.ref} onScroll={persist.onScroll} />
    );
}

describe('usePersistScroll', () => {
    it('restores the stored scrollTop onto a newly mounted node', () => {
        const storeRef = { current: 80 };
        const { getByTestId } = render(<Probe storeRef={storeRef} />);
        expect(getByTestId('scroller').scrollTop).toBe(80);
    });

    it('writes scroll position into the store and reapplies it on orientationchange', () => {
        const storeRef = { current: 0 };
        const { getByTestId } = render(<Probe storeRef={storeRef} />);
        const el = getByTestId('scroller');
        Object.defineProperty(el, 'scrollTop', { value: 120, writable: true, configurable: true });
        fireEvent.scroll(el);
        expect(storeRef.current).toBe(120);

        el.scrollTop = 0;
        act(() => {
            window.dispatchEvent(new Event('orientationchange'));
        });
        expect(el.scrollTop).toBe(120);
    });
});
