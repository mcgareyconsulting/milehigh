/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Raw-PCM audio plumbing for live Carmen. The realtime API speaks 24 kHz signed
 *          16-bit PCM in both directions, which MediaRecorder cannot produce and <audio>
 *          cannot play gaplessly — so capture goes through an AudioWorklet and playback
 *          through scheduled AudioBuffers on a running clock.
 * exports:
 *   MicCapture: mic -> 24 kHz PCM16 base64 chunks via onChunk.
 *   PcmPlayer: queue base64 PCM16 chunks and play them back-to-back; clear() for barge-in.
 *   pcm16ToBase64 / base64ToFloat32: the encoding pair used on the wire.
 * imports_from: []
 * imported_by: [hooks/useCarmenLive.js]
 * invariants:
 *   - Everything runs at RATE (24000); if the browser refuses that context rate we
 *     linearly resample rather than sending audio at the wrong speed.
 *   - PcmPlayer.clear() must drop scheduled sources immediately — a barge-in that keeps
 *     talking over the user is the single worst failure mode in a live call.
 *   - Both classes release the mic/context on close(); nothing may outlive the session.
 */

export const RATE = 24000;

// ~42ms of audio per message: small enough that barge-in feels instant, large enough
// that we're not posting 180 WebSocket frames a second.
const FRAMES_PER_CHUNK = 1024;

const WORKLET_SOURCE = `
class CarmenCapture extends AudioWorkletProcessor {
    constructor() {
        super();
        this._buf = new Float32Array(${FRAMES_PER_CHUNK});
        this._n = 0;
    }
    process(inputs) {
        const ch = inputs[0] && inputs[0][0];
        if (!ch) return true;
        for (let i = 0; i < ch.length; i += 1) {
            this._buf[this._n] = ch[i];
            this._n += 1;
            if (this._n === this._buf.length) {
                this.port.postMessage(this._buf.slice(0));
                this._n = 0;
            }
        }
        return true;
    }
}
registerProcessor('carmen-capture', CarmenCapture);
`;

/** Float32 [-1,1] -> base64 of little-endian PCM16. */
export function pcm16ToBase64(float32) {
    const pcm = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i += 1) {
        const s = Math.max(-1, Math.min(1, float32[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    const bytes = new Uint8Array(pcm.buffer);
    let binary = '';
    // Chunked so a long buffer can't blow the argument limit on fromCharCode.
    for (let i = 0; i < bytes.length; i += 0x8000) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary);
}

/** base64 of little-endian PCM16 -> Float32 [-1,1]. */
export function base64ToFloat32(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const pcm = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
    const out = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i += 1) out[i] = pcm[i] / 0x8000;
    return out;
}

/** Cheap linear resample — only used when a browser won't give us a 24 kHz context. */
function resample(input, fromRate, toRate) {
    if (fromRate === toRate) return input;
    const ratio = fromRate / toRate;
    const out = new Float32Array(Math.round(input.length / ratio));
    for (let i = 0; i < out.length; i += 1) {
        const pos = i * ratio;
        const lo = Math.floor(pos);
        const hi = Math.min(lo + 1, input.length - 1);
        out[i] = input[lo] + (input[hi] - input[lo]) * (pos - lo);
    }
    return out;
}

export class MicCapture {
    constructor({ onChunk, onLevel } = {}) {
        this.onChunk = onChunk;
        this.onLevel = onLevel;
        this.ctx = null;
        this.stream = null;
        this.node = null;
        this.source = null;
    }

    async start() {
        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,   // without this she hears herself and interrupts herself
                noiseSuppression: true,
                autoGainControl: true,
                channelCount: 1,
            },
        });
        this.ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: RATE });
        if (this.ctx.state === 'suspended') await this.ctx.resume();

        const blob = new Blob([WORKLET_SOURCE], { type: 'application/javascript' });
        const url = URL.createObjectURL(blob);
        try {
            await this.ctx.audioWorklet.addModule(url);
        } finally {
            URL.revokeObjectURL(url);
        }

        this.source = this.ctx.createMediaStreamSource(this.stream);
        this.node = new AudioWorkletNode(this.ctx, 'carmen-capture');
        this.node.port.onmessage = (e) => {
            const frames = resample(e.data, this.ctx.sampleRate, RATE);
            if (this.onLevel) {
                let peak = 0;
                for (let i = 0; i < frames.length; i += 1) peak = Math.max(peak, Math.abs(frames[i]));
                this.onLevel(peak);
            }
            this.onChunk?.(pcm16ToBase64(frames));
        };
        this.source.connect(this.node);
        // A worklet with no destination is allowed to be culled; a muted gain keeps the
        // graph alive without routing the mic to the speakers.
        const mute = this.ctx.createGain();
        mute.gain.value = 0;
        this.node.connect(mute).connect(this.ctx.destination);
    }

    close() {
        try { this.node?.port?.close(); } catch { /* already gone */ }
        try { this.source?.disconnect(); this.node?.disconnect(); } catch { /* already gone */ }
        this.stream?.getTracks().forEach((t) => t.stop());
        this.ctx?.close().catch(() => {});
        this.ctx = null;
        this.stream = null;
        this.node = null;
        this.source = null;
    }
}

export class PcmPlayer {
    constructor({ onStateChange } = {}) {
        this.ctx = null;
        this.sources = new Set();
        this.playhead = 0;
        this.onStateChange = onStateChange;
        this._speaking = false;
    }

    _ensure() {
        if (!this.ctx) {
            this.ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: RATE });
            this.playhead = 0;
        }
        if (this.ctx.state === 'suspended') this.ctx.resume().catch(() => {});
        return this.ctx;
    }

    _setSpeaking(v) {
        if (this._speaking === v) return;
        this._speaking = v;
        this.onStateChange?.(v);
    }

    /** Queue one base64 PCM16 chunk to play immediately after whatever is already queued. */
    push(b64) {
        const frames = base64ToFloat32(b64);
        if (!frames.length) return;
        const ctx = this._ensure();
        const buffer = ctx.createBuffer(1, frames.length, RATE);
        buffer.copyToChannel(frames, 0);

        const src = ctx.createBufferSource();
        src.buffer = buffer;
        src.connect(ctx.destination);

        // A small lead keeps the first chunk from landing in the past on a slow frame.
        const startAt = Math.max(this.playhead, ctx.currentTime + 0.04);
        src.start(startAt);
        this.playhead = startAt + buffer.duration;

        this.sources.add(src);
        this._setSpeaking(true);
        src.onended = () => {
            this.sources.delete(src);
            if (this.sources.size === 0) this._setSpeaking(false);
        };
    }

    /** Barge-in: drop everything queued so she stops mid-word when the user speaks. */
    clear() {
        this.sources.forEach((s) => {
            try { s.onended = null; s.stop(); } catch { /* already finished */ }
        });
        this.sources.clear();
        this.playhead = this.ctx ? this.ctx.currentTime : 0;
        this._setSpeaking(false);
    }

    close() {
        this.clear();
        this.ctx?.close().catch(() => {});
        this.ctx = null;
    }
}
