import { useEffect, useRef, useState } from 'react';

// Ported from the Welding Boy design loop.jsx — random sequence driver.
// step indices: 0=IDLE, 1=PREP, 2=WAVE, 3=BACK, 4=MASK, 5=WELD

const rng = (min, max) => min + Math.random() * (max - min);
const pickN = (min, max) => Math.round(rng(min, max));

function actIdle(longish) {
    const dur = longish ? pickN(900, 1800) : pickN(500, 1100);
    return [{ f: 1, dur, step: 0 }];
}

function actBreathe() {
    return [
        { f: 1, dur: pickN(400, 800), step: 0 },
        { f: 2, dur: pickN(120, 220), step: 1 },
        { f: 1, dur: pickN(300, 700), step: 0 },
    ];
}

function actWave() {
    return [
        { f: 2, dur: pickN(160, 260), step: 1 },
        { f: 3, dur: pickN(700, 1500), step: 2 },
        { f: 4, dur: pickN(140, 240), step: 3 },
        { f: 1, dur: pickN(200, 500), step: 0 },
    ];
}

function actDoubleWave() {
    return [
        { f: 2, dur: pickN(140, 200), step: 1 },
        { f: 3, dur: pickN(280, 400), step: 2 },
        { f: 4, dur: pickN(140, 200), step: 3 },
        { f: 3, dur: pickN(280, 400), step: 2 },
        { f: 4, dur: pickN(140, 200), step: 3 },
        { f: 1, dur: pickN(200, 400), step: 0 },
    ];
}

function actWeld() {
    const bursts = pickN(2, 4);
    const seq = [{ f: 5, dur: pickN(280, 420), step: 4 }];
    for (let i = 0; i < bursts; i++) {
        const burstLen = pickN(220, 380);
        seq.push({ f: 6, dur: burstLen, step: 5, sparks: true, glow: true });
        if (i < bursts - 1) {
            seq.push({ f: 5, dur: pickN(80, 140), step: 5, sparks: true, glow: true });
        }
    }
    seq.push({ f: 5, dur: pickN(300, 500), step: 4 });
    seq.push({ f: 1, dur: pickN(400, 800), step: 0 });
    return seq;
}

function actFlex() {
    return [
        { f: 2, dur: pickN(180, 260), step: 1 },
        { f: 1, dur: pickN(140, 200), step: 0 },
        { f: 2, dur: pickN(180, 260), step: 1 },
        { f: 1, dur: pickN(400, 700), step: 0 },
    ];
}

const POOL = [
    { fn: actIdle, weight: 2, args: [false] },
    { fn: actBreathe, weight: 2 },
    { fn: actWave, weight: 4 },
    { fn: actDoubleWave, weight: 1 },
    { fn: actFlex, weight: 2 },
    { fn: actWeld, weight: 4 },
];
const TOTAL_WEIGHT = POOL.reduce((a, x) => a + x.weight, 0);

function pickAction() {
    let r = Math.random() * TOTAL_WEIGHT;
    for (const x of POOL) {
        r -= x.weight;
        if (r <= 0) return x;
    }
    return POOL[POOL.length - 1];
}

function buildRandomSequence() {
    const count = pickN(1, 3);
    let seq = [];
    let last = null;
    for (let i = 0; i < count; i++) {
        let p = pickAction();
        if (last && p.fn === last) p = pickAction();
        seq = seq.concat(p.fn(...(p.args || [])));
        last = p.fn;
    }
    return seq.concat(actIdle(true));
}

export function useBananaBoyLoop(enabled) {
    const [frame, setFrame] = useState(1);
    const [sparks, setSparks] = useState(false);
    const [glow, setGlow] = useState(false);

    const sequenceRef = useRef(null);
    const idxRef = useRef(0);
    const stepStartRef = useRef(0);
    const rafRef = useRef(0);

    useEffect(() => {
        if (!enabled) {
            setFrame(1);
            setSparks(false);
            setGlow(false);
            return undefined;
        }

        sequenceRef.current = buildRandomSequence();
        idxRef.current = 0;
        stepStartRef.current = performance.now();

        const applyStep = (i) => {
            const seq = sequenceRef.current;
            const step = seq[i];
            setFrame(step.f);
            setSparks(!!step.sparks);
            setGlow(!!step.glow);
        };
        applyStep(0);

        const tick = (now) => {
            const seq = sequenceRef.current;
            const cur = seq[idxRef.current];
            if (now - stepStartRef.current >= cur.dur) {
                stepStartRef.current = now;
                idxRef.current += 1;
                if (idxRef.current >= seq.length) {
                    sequenceRef.current = buildRandomSequence();
                    idxRef.current = 0;
                }
                applyStep(idxRef.current);
            }
            rafRef.current = requestAnimationFrame(tick);
        };

        rafRef.current = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafRef.current);
    }, [enabled]);

    return { frame, sparks, glow };
}
