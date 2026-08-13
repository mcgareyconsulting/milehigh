/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Registers Carlito (the metric-compatible stand-in for Calibri) with a jsPDF document so exported PDFs are set in the same face as the on-screen tables, falling back to a built-in core if the font files can't be fetched.
 * exports:
 *   ensureTableFonts: async (doc) => family name to pass as styles.font
 *   TABLE_FONT_FALLBACK: the family used when the fonts are unavailable
 * imports_from: []
 * imported_by: [frontend/src/utils/jobLogPdf.js]
 * invariants:
 *   - Never throws. A failed fetch degrades to Helvetica and still produces a PDF.
 *   - The .ttf files are generated from the @fontsource WOFFs by scripts/build_pdf_fonts.py;
 *     they are not checked-in third-party binaries to edit by hand.
 *   - Base64 payloads are cached per page load — a second export re-registers from memory.
 */

// Served from frontend/public/fonts (Vite copies public/ into dist/, and Flask
// serves any file that exists under dist/, same as /icons/*.png).
//
// Calibri itself is Microsoft-licensed and can't be embedded in a PDF we ship,
// so the export embeds Carlito: same advance widths, same shapes, OFL. A print
// set in Carlito and one set in Calibri lay out line-for-line identically.
const FACES = [
    { file: 'carlito-400.ttf', family: 'Carlito', style: 'normal' },
    { file: 'carlito-700.ttf', family: 'Carlito', style: 'bold' },
];

// jsPDF's Standard-14 cores. Helvetica is what this export used before the
// screen moved off the system stack, so falling back here produces a plain but
// correct document rather than something broken.
export const TABLE_FONT_FALLBACK = 'helvetica';
const EMBEDDED = 'Carlito';

function toBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    // btoa needs a binary string. Building it in chunks keeps the argument list
    // to String.fromCharCode small enough to avoid a call-stack overflow on the
    // ~46KB faces.
    const CHUNK = 8192;
    let binary = '';
    for (let i = 0; i < bytes.length; i += CHUNK) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
    }
    return btoa(binary);
}

// Resolves to [{ file, family, style, base64 }] or null if any face is
// unreachable. Kept as a single promise so concurrent exports share one fetch.
let _facesPromise = null;

function loadFaces() {
    if (!_facesPromise) {
        _facesPromise = Promise.all(
            FACES.map(async (face) => {
                const res = await fetch(`/fonts/${face.file}`);
                if (!res.ok) throw new Error(`${face.file}: HTTP ${res.status}`);
                const buf = await res.arrayBuffer();
                // A SPA catch-all that serves index.html for a missing asset
                // returns 200 with HTML, which would register as a font and
                // render every glyph blank. Check the sfnt magic instead of
                // trusting the status.
                const magic = new DataView(buf).getUint32(0);
                if (magic !== 0x00010000 && magic !== 0x74727565) {
                    throw new Error(`${face.file}: not a TrueType file`);
                }
                return { ...face, base64: toBase64(buf) };
            }),
        ).catch((err) => {
            console.warn('[pdf] table fonts unavailable, falling back to Helvetica:', err.message);
            // Don't cache the failure as a rejected promise — a later export
            // (after a deploy, or once back online) should get to retry.
            _facesPromise = null;
            return null;
        });
    }
    return _facesPromise;
}

/**
 * Register the table face with `doc` and return the family name to set as
 * `styles.font`. Returns TABLE_FONT_FALLBACK if the fonts could not be loaded,
 * so callers can use the result unconditionally.
 */
export async function ensureTableFonts(doc) {
    const faces = await loadFaces();
    if (!faces) return TABLE_FONT_FALLBACK;
    try {
        for (const { file, family, style, base64 } of faces) {
            doc.addFileToVFS(file, base64);
            doc.addFont(file, family, style);
        }
        return EMBEDDED;
    } catch (err) {
        console.warn('[pdf] could not register table fonts with jsPDF:', err.message);
        return TABLE_FONT_FALLBACK;
    }
}
