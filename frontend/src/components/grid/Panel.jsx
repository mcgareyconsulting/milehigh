/**
 * @milehigh-header
 * schema_version: 3
 * purpose: The box in the K2 grid engine — one panel's chrome, in both normal and edit mode.
 *   Chrome geometry and type scale are lifted from docs/projects-page-mockup.html (`.panel`,
 *   `.panel-header`, `.panel-title`, `.drag-handle`, `.dot`): 10px radius, 1px border, a
 *   13px/700 title that turns accent on header hover, an 8px status dot, and a ⠿ handle.
 *   Colours come from gridTheme.css tokens, never literals, so the same panel renders light
 *   on the app's surfaces and dark on the Projects page. Edit mode is the widget-arranging
 *   layer: the panel is outlined, the whole surface becomes the drag target, a ✕ removes it,
 *   and chips snap its width and height to the grid's size classes. A `kpi` variant strips
 *   the header entirely for stat tiles.
 * exports:
 *   Panel: presentational panel chrome (no drag wiring)
 *   SortablePanel: Panel wrapped in @dnd-kit useSortable
 * imports_from: [@dnd-kit/sortable, @dnd-kit/utilities, ./layoutMerge]
 * imported_by: [components/grid/PanelGrid.jsx]
 * invariants:
 *   - Normal mode: only the ⠿ handle starts a drag, so the header stays clickable for
 *     drill-through. Edit mode: the whole panel drags and drill-through is disabled.
 *   - span/rows are always one of the panel's allowed sizes (enforced by mergeLayout).
 *   - No colour literals here — every colour is a var(--k2-*) from gridTheme.css.
 */
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { DEFAULT_SIZES, DEFAULT_ROW_SIZES } from './layoutMerge';

// Tailwind can't see dynamically-built class names, so span classes are enumerated.
const SPAN_CLASS = {
  1: '',
  2: 'md:col-span-2',
  3: 'md:col-span-2 lg:col-span-3',
};

// Height is quantized to grid row units (see ROW_UNIT_PX in PanelGrid) so panels line up
// in bands instead of drifting to whatever their content happens to measure.
const ROW_CLASS = {
  1: 'row-span-1',
  2: 'row-span-2',
  3: 'row-span-3',
  4: 'row-span-4',
};

// The mockup's `.dot-*` set, verbatim — these are a fixed vocabulary, not theme tokens, so
// a panel's identity colour reads the same wherever the grid is rendered.
const DOT_CLASS = {
  blue: 'bg-[#3b82f6]',
  green: 'bg-[#22c55e]',
  yellow: 'bg-[#eab308]',
  orange: 'bg-[#f97316]',
  red: 'bg-[#ef4444]',
  purple: 'bg-[#a855f7]',
  pink: 'bg-[#ec4899]',
  teal: 'bg-[#14b8a6]',
  indigo: 'bg-[#6366f1]',
  cyan: 'bg-[#06b6d4]',
  gray: 'bg-[#64748b]',
};

const WIDTH_LABEL = { 1: 'S', 2: 'M', 3: 'L' };

function SizeChips({ sizes, current, onPick, kind, labels }) {
  if (sizes.length < 2) return null; // nothing to choose
  return (
    <div className="flex items-center gap-1" onPointerDown={e => e.stopPropagation()}>
      <span className="text-[10px] text-[var(--k2-faint)] mr-0.5" aria-hidden="true">
        {kind === 'Width' ? '↔' : '↕'}
      </span>
      {sizes.map(s => (
        <button
          key={s}
          type="button"
          onClick={e => { e.stopPropagation(); onPick(s); }}
          aria-label={`${kind} ${labels ? labels[s] : s}`}
          aria-pressed={current === s}
          className={`w-6 h-6 rounded text-[10px] font-bold transition-colors ${
            current === s
              ? 'bg-[var(--k2-accent-strong)] text-white'
              : 'bg-[var(--k2-chip)] text-[var(--k2-muted)] hover:text-[var(--k2-title)]'
          }`}
        >
          {labels ? labels[s] : s}
        </button>
      ))}
    </div>
  );
}

export function Panel({
  id,
  title,
  dot,
  span = 1,
  rows = 2,
  variant,
  onOpen,
  headerAction,
  children,
  empty,
  isEmpty = false,
  sizes,
  rowSizes,
  // Edit-mode wiring
  editing = false,
  onSetSpan,
  onSetRows,
  onHide,
  // Drag wiring
  isDragging = false,
  dragHandleProps,
  innerRef,
  style,
}) {
  const spanClass = SPAN_CLASS[span] !== undefined ? SPAN_CLASS[span] : SPAN_CLASS[1];
  const rowClass = ROW_CLASS[rows] !== undefined ? ROW_CLASS[rows] : ROW_CLASS[2];
  const allowedWidths = (Array.isArray(sizes) && sizes.length ? sizes : DEFAULT_SIZES)
    .filter(s => DEFAULT_SIZES.includes(s));
  const allowedHeights = (Array.isArray(rowSizes) && rowSizes.length ? rowSizes : DEFAULT_ROW_SIZES)
    .filter(s => DEFAULT_ROW_SIZES.includes(s));
  // Drill-through is suppressed while editing — in edit mode a tap rearranges, it doesn't open.
  const clickable = typeof onOpen === 'function' && !editing;
  const isKpi = variant === 'kpi';

  return (
    <div
      ref={innerRef}
      style={style}
      data-panel-id={id}
      // In edit mode the whole panel is the drag surface; in normal mode only
      // the ⠿ handle is, so headers stay clickable.
      {...(editing ? dragHandleProps : {})}
      // h-full + min-h-0 make the panel fill its quantized grid area exactly, so the body
      // can scroll instead of stretching the row.
      className={`${spanClass} ${rowClass} h-full min-w-0 min-h-0 flex flex-col overflow-hidden
        rounded-[10px] border bg-[var(--k2-panel)]
        ${editing
          ? 'border-dashed border-[var(--k2-accent)] cursor-grab active:cursor-grabbing select-none touch-none'
          : 'border-[var(--k2-border)]'}
        ${isDragging
          // The mockup's `.sortable-drag`: the moving panel lifts off the page. dnd-kit
          // moves the real element (no clone), so the lift goes here, not on a placeholder.
          ? 'shadow-[0_8px_32px_#000a] z-10 relative'
          : ''}`}
    >
      {/* Edit-mode toolbar: remove + width/height classes. Replaces the header on KPI tiles. */}
      {editing && (
        <div className="flex items-center justify-between gap-2 px-2 py-1.5 shrink-0 border-b border-dashed border-[var(--k2-border)]">
          <div className="flex items-center gap-2 min-w-0 overflow-x-auto">
            <SizeChips
              kind="Width" labels={WIDTH_LABEL}
              sizes={allowedWidths} current={span} onPick={s => onSetSpan?.(s)}
            />
            {allowedWidths.length > 1 && allowedHeights.length > 1 && (
              <span className="w-px h-4 bg-[var(--k2-border)] shrink-0" />
            )}
            <SizeChips
              kind="Height"
              sizes={allowedHeights} current={rows} onPick={s => onSetRows?.(s)}
            />
          </div>
          <button
            type="button"
            onPointerDown={e => e.stopPropagation()}
            onClick={e => { e.stopPropagation(); onHide?.(); }}
            aria-label={`Remove ${title}`}
            className="w-6 h-6 shrink-0 rounded-full bg-[var(--k2-chip)] text-[var(--k2-muted)]
              hover:bg-[#ef4444] hover:text-white transition-colors text-xs font-bold leading-none"
          >
            ✕
          </button>
        </div>
      )}

      {!isKpi && (
        // Mockup `.panel-header`: 12px 14px 10px, 1px bottom rule, title goes accent on hover.
        <div
          className={`flex items-center justify-between gap-2 pl-[14px] pr-[14px] pt-3 pb-2.5 shrink-0
            border-b border-[var(--k2-border)] ${clickable ? 'cursor-pointer group' : ''}`}
          onClick={clickable ? onOpen : undefined}
          onKeyDown={clickable ? (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); }
          } : undefined}
          role={clickable ? 'button' : undefined}
          tabIndex={clickable ? 0 : undefined}
        >
          <div className="flex items-center gap-[7px] min-w-0">
            {/* Normal mode: drag is handle-only so the rest of the header keeps its
                click-to-open behavior. Edit mode drags from anywhere, so the handle hides. */}
            {!editing && (
              <span
                {...dragHandleProps}
                onClick={(e) => e.stopPropagation()}
                className="shrink-0 text-sm leading-none text-[var(--k2-handle)] hover:text-[var(--k2-handle-hover)]
                  cursor-grab active:cursor-grabbing select-none touch-none"
                title="Drag to rearrange"
                aria-label="Drag to rearrange panel"
              >
                ⠿
              </span>
            )}
            {dot && <span className={`shrink-0 w-2 h-2 rounded-full ${DOT_CLASS[dot] || DOT_CLASS.gray}`} />}
            <span className={`text-[13px] font-bold tracking-[0.3px] truncate transition-colors
              text-[var(--k2-title)] ${clickable ? 'group-hover:text-[var(--k2-accent)]' : ''}`}>
              {title}
            </span>
          </div>

          {headerAction && !editing && (
            // The action slot is deliberately separate from the drill-through: clicking it
            // must not open the modal.
            <span className="shrink-0" onClick={(e) => e.stopPropagation()}>
              {headerAction}
            </span>
          )}
        </div>
      )}

      {/* min-h-0 lets this flex child shrink below its content, which is what makes
          overflow-y-auto actually scroll instead of the panel growing past its row span. */}
      <div className={`flex-1 min-w-0 min-h-0 overflow-y-auto text-[var(--k2-text)] ${isKpi ? 'p-3' : 'px-[14px] py-3'}`}>
        {isEmpty
          ? (empty ?? <p className="py-6 text-center text-xs text-[var(--k2-muted)]">Nothing to show yet.</p>)
          : children}
      </div>
    </div>
  );
}

export function SortablePanel({ panel, span, rows, editing, onSetSpan, onSetRows, onHide }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: panel.id });

  return (
    <Panel
      {...panel}
      span={span}
      rows={rows}
      editing={editing}
      onSetSpan={onSetSpan}
      onSetRows={onSetRows}
      onHide={onHide}
      innerRef={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      isDragging={isDragging}
      dragHandleProps={{ ...attributes, ...listeners }}
    >
      {/* render() receives its current size so a panel can show MORE at a bigger size —
          resizing is how the user asks for more of a list, not just a bigger box. */}
      {typeof panel.render === 'function' ? panel.render({ span, rows }) : panel.children}
    </Panel>
  );
}
