/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Urgency progress bar showing a row of tiled banana-boy pixel-art characters that fill in left-to-right as a release advances.
 * exports:
 *   BananaIcon: Progress indicator. Props: progress (0-1), width, height.
 * imports_from: [react]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - progress clamped to [0, 1]
 *   - Single shared PNG tiled via backgroundRepeat — browser fetches and decodes once per page
 *   - Pixel-art rendering uses image-rendering: pixelated so the tiny character stays crisp
 *   - Unfilled tiles shown at low opacity; filled portion revealed via clip-path from the right
 * updated_by_agent: 2026-04-20T00:00:00Z
 */
import React from 'react';

const IMG_SRC = '/banana-boy.png';
const UNFILLED_OPACITY = 0.22;

export function BananaIcon({ progress = 0, width = 140, height = 36 }) {
    const clamped = Math.max(0, Math.min(1, Number.isFinite(progress) ? progress : 0));
    const percent = Math.round(clamped * 100);
    const ariaLabel = `Release progress: ${percent}%`;

    // Reveal from the right inward — the filled portion grows left-to-right.
    const revealClip = `inset(0 ${(1 - clamped) * 100}% 0 0)`;

    // Tile the pixel-art banana vertically-fit, repeating horizontally so the
    // whole column fills with a line of banana-boys.
    const bgStyle = {
        backgroundImage: `url(${IMG_SRC})`,
        backgroundSize: 'auto 100%',
        backgroundRepeat: 'repeat-x',
        backgroundPosition: 'left center',
        imageRendering: 'pixelated',
    };

    return (
        <div
            role="img"
            aria-label={ariaLabel}
            title={ariaLabel}
            style={{
                position: 'relative',
                width,
                height,
                display: 'inline-block',
                verticalAlign: 'middle',
                overflow: 'hidden',
                borderRadius: 4,
            }}
        >
            <div
                style={{
                    position: 'absolute',
                    inset: 0,
                    opacity: UNFILLED_OPACITY,
                    ...bgStyle,
                    pointerEvents: 'none',
                }}
            />
            {clamped > 0 && (
                <div
                    style={{
                        position: 'absolute',
                        inset: 0,
                        clipPath: revealClip,
                        WebkitClipPath: revealClip,
                        ...bgStyle,
                        pointerEvents: 'none',
                    }}
                />
            )}
        </div>
    );
}
