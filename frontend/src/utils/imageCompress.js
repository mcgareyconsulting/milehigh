/**
 * Downscale/re-encode a photo in the browser before upload.
 *
 * Phone cameras produce 3–12 MB images; over LTE that can take longer than the
 * server is willing to wait for a request body. Re-encoding to a bounded JPEG
 * cuts the payload ~10x with no visible loss for job-site photos.
 *
 * Best-effort: any failure (unsupported format such as HEIC in a browser that
 * can't decode it, canvas errors, tiny files) returns the original File.
 */

const MAX_EDGE_PX = 2048;
const JPEG_QUALITY = 0.85;
// Files already this small aren't worth re-encoding.
const SKIP_BELOW_BYTES = 600 * 1024;

async function decode(file) {
    if (typeof createImageBitmap === 'function') {
        try {
            // imageOrientation:'from-image' applies EXIF rotation so phone shots don't come out sideways.
            return await createImageBitmap(file, { imageOrientation: 'from-image' });
        } catch {
            /* fall through to <img> */
        }
    }
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
        img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decode failed')); };
        img.src = url;
    });
}

export async function compressImage(file, { maxEdge = MAX_EDGE_PX, quality = JPEG_QUALITY } = {}) {
    if (!file || !(file instanceof Blob)) return file;
    if (file.size < SKIP_BELOW_BYTES) return file;
    if (file.type === 'image/gif') return file; // would drop animation

    try {
        const source = await decode(file);
        const srcW = source.width || source.naturalWidth;
        const srcH = source.height || source.naturalHeight;
        if (!srcW || !srcH) return file;

        const scale = Math.min(1, maxEdge / Math.max(srcW, srcH));
        const w = Math.round(srcW * scale);
        const h = Math.round(srcH * scale);

        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(source, 0, 0, w, h);
        if (typeof source.close === 'function') source.close();

        const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
        if (!blob || blob.size >= file.size) return file;

        const base = (file.name || 'photo').replace(/\.[^.]+$/, '');
        return new File([blob], `${base}.jpg`, { type: 'image/jpeg', lastModified: file.lastModified || Date.now() });
    } catch {
        return file;
    }
}
