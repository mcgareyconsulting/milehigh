import { describe, it, expect } from 'vitest';
import { formatInstallProg } from './JobDetailsBody.jsx';

describe('formatInstallProg', () => {
    it('appends % to whole numbers', () => {
        expect(formatInstallProg(75)).toBe('75%');
        expect(formatInstallProg('75')).toBe('75%');
        expect(formatInstallProg('0')).toBe('0%');
        expect(formatInstallProg('100')).toBe('100%');
    });

    it('keeps X as X', () => {
        expect(formatInstallProg('X')).toBe('X');
        expect(formatInstallProg('x')).toBe('X');
    });

    it('treats blank and O as empty', () => {
        expect(formatInstallProg(null)).toBeNull();
        expect(formatInstallProg('')).toBeNull();
        expect(formatInstallProg('O')).toBeNull();
        expect(formatInstallProg('o')).toBeNull();
    });

    it('does not invent % for decimals or junk', () => {
        expect(formatInstallProg('0.75')).toBe('0.75');
        expect(formatInstallProg('75.5')).toBe('75.5');
        expect(formatInstallProg('half')).toBe('half');
    });
});
