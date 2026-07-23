/**
 * @milehigh-header
 * schema_version: 2
 * purpose: The box in the K2 grid engine — one panel's chrome, in both normal and edit mode.
 *   Normal mode implements the box contract from Bill's UI spec: drag handle, status dot,
 *   title, a right-aligned header action slot distinct from the drill-through, a body, and an
 *   optional empty state. Edit mode is the widget-arranging layer: the panel is outlined, the whole
 *   surface becomes the drag target, a ✕ removes it, and chips snap its width and height to
 *   the grid's size classes. A `kpi` variant strips the header entirely for stat tiles.
 * exports:
 *   Panel: presentational panel chrome (no drag wiring)
 *   SortablePanel: Panel wrapped in @dnd-kit useSortable
 * imports_from: [@dnd-kit/sortable, @dnd-kit/utilities, ./layoutMerge]
 * imported_by: [components/grid/PanelGrid.jsx]
 * invariants:
 *   - Normal mode: only the ⠿ handle starts a drag, so the header stays clickable for
 *     drill-through. Edit mode: the whole panel drags and drill-through is disabled.
 *   - span/rows are always one of the panel's allowed sizes (enforced by mergeLayout).
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

const DOT_CLASS = {
  blue: 'bg-accent-500',
  green: 'bg-green-500',
  yellow: 'bg-amber-400',
  orange: 'bg-orange-500',
  red: 'bg-red-500',
  purple: 'bg-purple-500',
  pink: 'bg-pink-500',
  teal: 'bg-teal-500',
  gray: 'bg-slate-400',
};

const WIDTH_LABEL = { 1: 'S', 2: 'M', 3: 'L' };

function SizeChips({ sizes, current, onPick, kind, labels }) {
  if (sizes.length < 2) return null; // nothing to choose
  return (
    <div className="flex items-center gap-1" onPointerDown={e => e.stopPropagation()}>
      <span className="text-[10px] text-gray-400 dark:text-slate-500 mr-0.5" aria-hidden="true">
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
              ? 'bg-accent-500 text-white'
              : 'bg-gray-100 dark:bg-slate-700 text-gray-500 dark:text-slate-300 hover:bg-gray-200 dark:hover:bg-slate-600'
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
        rounded-lg border bg-white dark:bg-slate-800 shadow-sm
        ${editing
          ? 'border-dashed border-accent-300 dark:border-accent-600 ring-1 ring-accent-200 dark:ring-accent-700 cursor-grab active:cursor-grabbing select-none touch-none'
          : 'border-gray-200 dark:border-slate-700 transition-shadow hover:shadow-md'}
        ${isDragging ? 'opacity-40' : ''}`}
    >
      {/* Edit-mode toolbar: remove + width/height classes. Replaces the header on KPI tiles. */}
      {editing && (
        <div className="flex items-center justify-between gap-2 px-2 py-1.5 shrink-0 border-b border-dashed border-accent-200 dark:border-accent-700">
          <div className="flex items-center gap-2 min-w-0 overflow-x-auto">
            <SizeChips
              kind="Width" labels={WIDTH_LABEL}
              sizes={allowedWidths} current={span} onPick={s => onSetSpan?.(s)}
            />
            {allowedWidths.length > 1 && allowedHeights.length > 1 && (
              <span className="w-px h-4 bg-gray-200 dark:bg-slate-600 shrink-0" />
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
            className="w-6 h-6 shrink-0 rounded-full bg-gray-200 dark:bg-slate-600 text-gray-600 dark:text-slate-200
              hover:bg-red-500 hover:text-white transition-colors text-xs font-bold leading-none"
          >
            ✕
          </button>
        </div>
      )}

      {!isKpi && (
        <div
          className={`flex items-center justify-between gap-2 px-3.5 py-2.5 shrink-0 border-b border-gray-100 dark:border-slate-700
            ${clickable ? 'cursor-pointer group' : ''}`}
          onClick={clickable ? onOpen : undefined}
          onKeyDown={clickable ? (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); }
          } : undefined}
          role={clickable ? 'button' : undefined}
          tabIndex={clickable ? 0 : undefined}
        >
          <div className="flex items-center gap-2 min-w-0">
            {/* Normal mode: drag is handle-only so the rest of the header keeps its
                click-to-open behavior. Edit mode drags from anywhere, so the handle hides. */}
            {!editing && (
              <span
                {...dragHandleProps}
                onClick={(e) => e.stopPropagation()}
                className="shrink-0 text-slate-300 dark:text-slate-600 hover:text-slate-500 dark:hover:text-slate-400
                  cursor-grab active:cursor-grabbing select-none text-sm leading-none touch-none"
                title="Drag to rearrange"
                aria-label="Drag to rearrange panel"
              >
                ⠿
              </span>
            )}
            {dot && <span className={`shrink-0 w-2 h-2 rounded-full ${DOT_CLASS[dot] || DOT_CLASS.gray}`} />}
            <span className={`text-sm font-semibold text-gray-800 dark:text-slate-100 truncate
              ${clickable ? 'group-hover:text-accent-600 dark:group-hover:text-accent-300' : ''}`}>
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
      <div className={`flex-1 min-w-0 min-h-0 overflow-y-auto ${isKpi ? 'p-3' : 'p-3.5'}`}>
        {isEmpty
          ? (empty ?? <p className="py-6 text-center text-xs text-gray-400 dark:text-slate-500">Nothing to show yet.</p>)
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
