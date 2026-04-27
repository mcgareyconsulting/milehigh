// Contract tests pinning the @mention regex used in app/brain/mentions.py.
// Any change here is a heads-up to update the backend regex too.
import { describe, it, expect } from 'vitest';
import { parseMentions } from './mentions.js';

describe('parseMentions', () => {
    it('extracts a simple first-name mention', () => {
        expect(parseMentions('hey @Alice take a look')).toEqual(['alice']);
    });

    it('extracts multiple mentions', () => {
        expect(parseMentions('@Alice and @Bob — fyi @Carol')).toEqual([
            'alice', 'bob', 'carol',
        ]);
    });

    it('lowercases for case-insensitive backend match', () => {
        expect(parseMentions('@ALICE @Alice @alice')).toEqual([
            'alice', 'alice', 'alice',
        ]);
    });

    it('matches \\w+ (digits and underscores)', () => {
        expect(parseMentions('@user_42')).toEqual(['user_42']);
    });

    it('does not match emails as mentions of the user', () => {
        // \w+ matches "example" inside "alice@example.com" — same as backend
        expect(parseMentions('email me at alice@example.com')).toEqual(['example']);
    });

    it('returns empty for empty/null/undefined input', () => {
        expect(parseMentions('')).toEqual([]);
        expect(parseMentions(null)).toEqual([]);
        expect(parseMentions(undefined)).toEqual([]);
    });

    it('matches a mention that is the entire string', () => {
        expect(parseMentions('@Bob')).toEqual(['bob']);
    });
});
