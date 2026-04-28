import { useEffect, useRef } from 'react';
import { useBananaBoyLoop } from './useBananaBoyLoop';
import { FRAMES, FRAME_SRC } from './frames';

export default function BananaBoyAnimation({ enabled = true, className = '' }) {
    const { frame, sparks, glow } = useBananaBoyLoop(enabled);
    const sparksRef = useRef(null);
    const lastSparkRef = useRef(0);
    const rafRef = useRef(0);
    const sparksOnRef = useRef(false);

    useEffect(() => {
        sparksOnRef.current = sparks;
    }, [sparks]);

    useEffect(() => {
        if (!enabled) return undefined;
        const sparksHost = sparksRef.current;

        const tick = (now) => {
            rafRef.current = requestAnimationFrame(tick);
            if (!sparksOnRef.current || !sparksHost) return;
            if (now - lastSparkRef.current < 50) return;
            lastSparkRef.current = now;

            const count = 1 + Math.floor(Math.random() * 2);
            for (let k = 0; k < count; k++) {
                const s = document.createElement('div');
                s.className = 'bb-spark';
                const angle = (-20 + Math.random() * 80) * Math.PI / 180;
                const dist = 18 + Math.random() * 32;
                const tx = Math.cos(angle) * dist;
                const ty = Math.sin(angle) * dist + 4;
                s.style.setProperty('--bb-tx', `${tx.toFixed(1)}px`);
                s.style.setProperty('--bb-ty', `${ty.toFixed(1)}px`);
                s.style.left = `${(Math.random() * 6 - 3).toFixed(0)}px`;
                s.style.top = `${(Math.random() * 4 - 2).toFixed(0)}px`;
                const hue = Math.random();
                if (hue > 0.85) s.style.background = '#ffe28a';
                else if (hue > 0.5) s.style.background = '#ffae3d';
                sparksHost.appendChild(s);
                window.setTimeout(() => s.remove(), 800);
            }
        };
        rafRef.current = requestAnimationFrame(tick);
        return () => {
            cancelAnimationFrame(rafRef.current);
            if (sparksHost) sparksHost.innerHTML = '';
        };
    }, [enabled]);

    return (
        <div className={`relative ${className}`} aria-hidden="true">
            <div
                className={`bb-glow ${glow ? 'bb-on' : ''}`}
                style={{
                    right: '12%',
                    bottom: '8%',
                    width: '70px',
                    height: '70px',
                    transform: 'translate(50%, 50%)',
                    opacity: glow ? undefined : 0,
                    zIndex: 1,
                }}
            />
            <div className="absolute inset-0 bb-breathe flex items-end justify-center" style={{ zIndex: 2 }}>
                <div className="relative h-full" style={{ aspectRatio: '222 / 325' }}>
                    {FRAMES.map((n) => (
                        <img
                            key={n}
                            src={FRAME_SRC(n)}
                            alt=""
                            className={`bb-frame bb-pixel ${frame === n ? 'bb-active' : ''}`}
                            draggable={false}
                        />
                    ))}
                    <div
                        ref={sparksRef}
                        className="absolute"
                        style={{ right: '14%', bottom: '12%', width: 0, height: 0, zIndex: 3 }}
                    />
                </div>
            </div>
        </div>
    );
}
