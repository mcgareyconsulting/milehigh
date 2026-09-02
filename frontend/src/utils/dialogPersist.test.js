import { describe, it, expect, beforeEach } from 'vitest';
import { persistOpenDialog, readOpenDialog } from './dialogPersist';

describe('dialogPersist', () => {
    beforeEach(() => {
        sessionStorage.clear();
    });

    it('round-trips a payload and clears on null', () => {
        persistOpenDialog('jl_hub', { id: 42, tab: 'attachments' });
        expect(readOpenDialog('jl_hub')).toEqual({ id: 42, tab: 'attachments' });
        persistOpenDialog('jl_hub', null);
        expect(readOpenDialog('jl_hub')).toBeNull();
    });

    it('returns null for missing or corrupt entries', () => {
        expect(readOpenDialog('missing')).toBeNull();
        sessionStorage.setItem('mhmw_open_dialog:jl_hub', '{not json');
        expect(readOpenDialog('jl_hub')).toBeNull();
    });
});
