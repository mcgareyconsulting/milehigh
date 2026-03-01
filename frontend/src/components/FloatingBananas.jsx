import { useEffect, useRef, useState } from 'react';

const BANANA_SIZE = 40;
const NUM_BANANAS = 14;
const BANANA_SPEED = 1.8;
const BURST_DURATION_MS = 2000;
const BURST_MULTIPLIER = 75;

function createItem(id, width, height, maxW, maxH) {
  return {
    id,
    width,
    height,
    x: Math.random() * (maxW - width),
    y: Math.random() * (maxH - height),
    vx: (Math.random() - 0.5) * 2 * BANANA_SPEED,
    vy: (Math.random() - 0.5) * 2 * BANANA_SPEED,
  };
}

function bounceOffWalls(item, containerWidth, containerHeight) {
  const { x, y, width, height, vx, vy } = item;
  let newVx = vx;
  let newVy = vy;
  let newX = x;
  let newY = y;

  if (x <= 0) {
    newVx = Math.abs(vx);
    newX = 0;
  } else if (x + width >= containerWidth) {
    newVx = -Math.abs(vx);
    newX = containerWidth - width;
  }
  if (y <= 0) {
    newVy = Math.abs(vy);
    newY = 0;
  } else if (y + height >= containerHeight) {
    newVy = -Math.abs(vy);
    newY = containerHeight - height;
  }

  item.x = newX;
  item.y = newY;
  item.vx = newVx;
  item.vy = newVy;
}

function bounceOffEachOther(a, b) {
  const ax = a.x + a.width / 2;
  const ay = a.y + a.height / 2;
  const bx = b.x + b.width / 2;
  const by = b.y + b.height / 2;
  const dx = bx - ax;
  const dy = by - ay;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const minDist = (a.width + b.width) / 2;
  if (dist >= minDist || dist === 0) return;

  const overlap = minDist - dist;
  const nx = dx / dist;
  const ny = dy / dist;
  const totalMass = a.width + b.width;
  const aMass = a.width / totalMass;
  const bMass = b.width / totalMass;

  a.x -= nx * overlap * bMass;
  a.y -= ny * overlap * bMass;
  b.x += nx * overlap * aMass;
  b.y += ny * overlap * aMass;

  const dvx = b.vx - a.vx;
  const dvy = b.vy - a.vy;
  const dvn = dvx * nx + dvy * ny;
  if (dvn >= 0) return;

  a.vx += (2 * bMass * dvn * nx) / (aMass + bMass);
  a.vy += (2 * bMass * dvn * ny) / (aMass + bMass);
  b.vx -= (2 * aMass * dvn * nx) / (aMass + bMass);
  b.vy -= (2 * aMass * dvn * ny) / (aMass + bMass);
}

export default function FloatingBananas({ className = '' }) {
  const containerRef = useRef(null);
  const itemsRef = useRef([]);
  const elementsRef = useRef([]);
  const frameRef = useRef(null);
  const [items, setItems] = useState([]);
  const [containerSize, setContainerSize] = useState({ width: 400, height: 300 });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) {
        setContainerSize({ width, height });
      }
    });
    ro.observe(container);

    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const { width, height } = containerSize;
    if (width < 50 || height < 50) return;

    const initial = Array.from({ length: NUM_BANANAS }, (_, i) =>
      createItem(`banana-${i}`, BANANA_SIZE, BANANA_SIZE, width, height)
    );
    itemsRef.current = initial.map((it) => ({ ...it }));
    setItems(initial);
  }, [containerSize.width, containerSize.height]);

  const handleBananaClick = (index) => {
    const refItem = itemsRef.current[index];
    if (!refItem) return;
    refItem.boostEndTime = Date.now() + BURST_DURATION_MS;
    refItem.boostMultiplier = BURST_MULTIPLIER;
  };

  useEffect(() => {
    const list = itemsRef.current;
    if (list.length === 0) return;

    const container = containerRef.current;
    if (!container) return;

    const W = containerSize.width;
    const H = containerSize.height;

    const loop = () => {
      const list = itemsRef.current;
      const now = Date.now();
      for (let i = 0; i < list.length; i++) {
        const it = list[i];
        const mult = (it.boostEndTime != null && now < it.boostEndTime) ? (it.boostMultiplier ?? 1) : 1;
        it.x += it.vx * mult;
        it.y += it.vy * mult;
        bounceOffWalls(it, W, H);
      }
      for (let i = 0; i < list.length; i++) {
        for (let j = i + 1; j < list.length; j++) {
          bounceOffEachOther(list[i], list[j]);
        }
      }
      const els = elementsRef.current;
      list.forEach((it, i) => {
        if (els[i]) {
          els[i].style.transform = `translate(${it.x}px,${it.y}px)`;
        }
      });
      frameRef.current = requestAnimationFrame(loop);
    };

    frameRef.current = requestAnimationFrame(loop);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [containerSize.width, containerSize.height, items.length]);

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full overflow-hidden ${className}`}
    >
      {items.map((item, i) => (
        <div
          key={item.id}
          ref={(el) => {
            if (el) elementsRef.current[i] = el;
          }}
          role="button"
          tabIndex={0}
          onClick={() => handleBananaClick(i)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleBananaClick(i);
            }
          }}
          className="absolute left-0 top-0 will-change-transform cursor-pointer touch-manipulation select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-1 rounded-full"
          style={{
            width: item.width,
            height: item.height,
            transform: `translate(${item.x}px,${item.y}px)`,
          }}
        >
          <img
            src="/bananas-svgrepo-com.svg"
            alt=""
            className="w-full h-full object-contain drop-shadow-md pointer-events-none"
            aria-hidden
          />
        </div>
      ))}
    </div>
  );
}
