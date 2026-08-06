/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Registers IBM Plex Sans/Mono with a jsPDF document so exported PDFs are set in the same faces as the on-screen tables, falling back to the built-in cores if the font files can't be fetched.
 * exports:
 *   ensurePlexFonts: async (doc) => { sans, mono } — jsPDF family names to pass as styles.font
 *   PLEX_FALLBACK: the { sans, mono } pair used when the fonts are unavailable
 * imports_from: []
 * imported_by: [frontend/src/utils/jobLogPdf.js]
 * invariants:
 *   - Never throws. A failed fetch degrades to Helvetica/Courier and still produces a PDF.
 *   - The .ttf files are generated from the @fontsource WOFFs by scripts/build_pdf_fonts.py;
 *     they are not checked-in third-party binaries to edit by hand.
 *   - Base64 payloads are cached per page load — a second export re-registers from memory.
 */

// Served from frontend/public/fonts (Vite copies public/ into dist/, and Flask
// serves any file that exists under dist/, same as /icons/*.png).
const FACES = [
    { file: 'ibm-plex-sans-400.ttf', family: 'IBMPlexSans', style: 'normal' },
    { file: 'ibm-plex-sans-700.ttf', family: 'IBMPlexSans', style: 'bold' },
    { file: 'ibm-plex-mono-400.ttf', family: 'IBMPlexMono', style: 'normal' },
    { file: 'ibm-plex-mono-700.ttf', family: 'IBMPlexMono', style: 'bold' },
];

// jsPDF's Standard-14 cores. Helvetica is what this export used before the
// screen moved to Plex, so falling back here reproduces the old output exactly
// rather than producing something broken.
export const PLEX_FALLBACK = { sans: 'helvetica', mono: 'courier' };
const PLEX = { sans: 'IBMPlexSans', mono: 'IBMPlexMono' };

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
            console.warn('[pdf] IBM Plex unavailable, falling back to Helvetica:', err.message);
            // Don't cache the failure as a rejected promise — a later export
            // (after a deploy, or once back online) should get to retry.
            _facesPromise = null;
            return null;
        });
    }
    return _facesPromise;
}

/**
 * Register IBM Plex with `doc` and return the family names to set as
 * `styles.font`. Returns PLEX_FALLBACK if the fonts could not be loaded, so
 * callers can use the result unconditionally.
 */
export async function ensurePlexFonts(doc) {
    const faces = await loadFaces();
    if (!faces) return PLEX_FALLBACK;
    try {
        for (const { file, family, style, base64 } of faces) {
            doc.addFileToVFS(file, base64);
            doc.addFont(file, family, style);
        }
        return PLEX;
    } catch (err) {
        console.warn('[pdf] could not register IBM Plex with jsPDF:', err.message);
        return PLEX_FALLBACK;
    }
}
