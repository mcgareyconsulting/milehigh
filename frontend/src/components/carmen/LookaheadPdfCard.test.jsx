import { describe, it, expect } from 'vitest';
import { extractLookaheadArtifacts } from './LookaheadPdfCard';

describe('extractLookaheadArtifacts', () => {
    it('prefers structured artifacts from the API', () => {
        const structured = [{
            kind: 'lookahead_pdf',
            download_path: '/brain/lookahead/artifacts/aaa.pdf',
            title: 'T',
        }];
        const out = extractLookaheadArtifacts(
            'also mentions /brain/lookahead/artifacts/bbb.pdf',
            structured,
        );
        expect(out).toHaveLength(1);
        expect(out[0].download_path).toContain('aaa.pdf');
    });

    it('scrapes download paths from assistant text when structured is empty', () => {
        const text = 'Ready: /brain/lookahead/artifacts/xyz_ABC-1.pdf — open that path.';
        const out = extractLookaheadArtifacts(text, []);
        expect(out).toHaveLength(1);
        expect(out[0].artifact_id).toBe('xyz_ABC-1');
        expect(out[0].download_path).toBe('/brain/lookahead/artifacts/xyz_ABC-1.pdf');
    });

    it('dedupes repeated paths in text', () => {
        const text = '/brain/lookahead/artifacts/x.pdf and again /brain/lookahead/artifacts/x.pdf';
        expect(extractLookaheadArtifacts(text)).toHaveLength(1);
    });
});
