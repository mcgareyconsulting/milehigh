/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Progress indicator showing banana-boy.jpg filling in left-to-right as a release advances.
 * exports:
 *   BananaIcon: Progress-fill banana-boy image. Props: progress (0-1), width, height.
 * imports_from: [react]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - progress is clamped to [0, 1]
 *   - Shared background-image — browser caches the file once; every row is just 2 plain divs
 *   - Unfilled portion is shown at low opacity; filled portion is full opacity, revealed left-to-right
 * updated_by_agent: 2026-04-20T00:00:00Z
 */
import React from 'react';

const IMG_SRC = '/banana-boy.jpg';
const UNFILLED_OPACITY = 0.22;

export function BananaIcon({ progress = 0, width = 140, height = 36 }) {
    const clamped = Math.max(0, Math.min(1, Number.isFinite(progress) ? progress : 0));
    const percent = Math.round(clamped * 100);
    const ariaLabel = `Release progress: ${percent}%`;

    // Reveal from the right inward to show progress building left-to-right.
    const revealClip = `inset(0 ${(1 - clamped) * 100}% 0 0)`;

    const bgStyle = {
        backgroundImage: `url(${IMG_SRC})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
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
