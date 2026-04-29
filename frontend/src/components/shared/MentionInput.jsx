/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides a text input or textarea with @mention autocomplete dropdown for tagging teammates.
 * exports:
 *   MentionInput: Controlled input/textarea that detects @-triggers, shows a filtered user dropdown, and inserts mention tokens
 * imports_from: [react]
 * imported_by: [components/board/BoardDetail.jsx, components/TableRow.jsx]
 * invariants:
 *   - Enter submits the form when the dropdown is closed; when open it selects the highlighted user
 *   - Dropdown uses fixed positioning; opens below the input and flips above when space is tight
 *   - multiline=true renders a <textarea>; otherwise an <input>. The imperative ref forwards to the underlying element.
 * updated_by_agent: 2026-04-17T00:00:00Z
 */
import { useState, useRef, useEffect, forwardRef, useImperativeHandle } from 'react';

const MentionInput = forwardRef(function MentionInput({
    value,
    onChange,
    onSubmit,
    onBlur,
    onCancel,
    users,
    placeholder,
    disabled,
    multiline = false,
    rows = 1,
    className,
}, ref) {
    const [showDropdown, setShowDropdown] = useState(false);
    const [filterText, setFilterText] = useState('');
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [triggerPos, setTriggerPos] = useState(null);
    const [dropdownStyle, setDropdownStyle] = useState(null);
    const inputRef = useRef(null);

    const updateDropdownPosition = () => {
        if (!inputRef.current) return;
        const rect = inputRef.current.getBoundingClientRect();
        const DROPDOWN_WIDTH = 260;
        const DROPDOWN_MAX_HEIGHT = 240;
        const viewportW = window.innerWidth;
        const viewportH = window.innerHeight;
        const spaceBelow = viewportH - rect.bottom;
        const spaceAbove = rect.top;
        const openUp = spaceBelow < DROPDOWN_MAX_HEIGHT + 8 && spaceAbove > spaceBelow;
        let left = rect.left;
        if (left + DROPDOWN_WIDTH > viewportW - 8) {
            left = Math.max(8, viewportW - DROPDOWN_WIDTH - 8);
        }
        const base = {
            position: 'fixed',
            left: `${left}px`,
            width: `${DROPDOWN_WIDTH}px`,
            maxHeight: `${DROPDOWN_MAX_HEIGHT}px`,
            zIndex: 1000,
        };
        setDropdownStyle(openUp
            ? { ...base, bottom: `${viewportH - rect.top + 4}px` }
            : { ...base, top: `${rect.bottom + 4}px` }
        );
    };

    useEffect(() => {
        if (!showDropdown) return;
        updateDropdownPosition();
        let rafId = null;
        const handler = () => {
            if (rafId !== null) return;
            rafId = requestAnimationFrame(() => {
                rafId = null;
                updateDropdownPosition();
            });
        };
        window.addEventListener('resize', handler);
        window.addEventListener('scroll', handler, { capture: true, passive: true });
        return () => {
            if (rafId !== null) cancelAnimationFrame(rafId);
            window.removeEventListener('resize', handler);
            window.removeEventListener('scroll', handler, { capture: true });
        };
    }, [showDropdown]);

    useImperativeHandle(ref, () => inputRef.current, []);

    useEffect(() => {
        if (!multiline) return;
        const el = inputRef.current;
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = `${el.scrollHeight}px`;
    }, [value, multiline]);

    const filtered = (users || []).filter(u => {
        const name = `${u.first_name} ${u.last_name}`.toLowerCase();
        return name.includes(filterText.toLowerCase());
    });

    useEffect(() => {
        setSelectedIndex(0);
    }, [filterText]);

    const handleChange = (e) => {
        const val = e.target.value;
        const cursor = e.target.selectionStart;
        onChange(val);

        const textBefore = val.slice(0, cursor);
        const atMatch = textBefore.match(/@(\w*)$/);
        if (atMatch) {
            setShowDropdown(true);
            setFilterText(atMatch[1]);
            setTriggerPos(atMatch.index);
        } else {
            setShowDropdown(false);
            setTriggerPos(null);
        }
    };

    const insertMention = (user) => {
        const before = value.slice(0, triggerPos);
        const afterCursor = inputRef.current.selectionStart;
        const after = value.slice(afterCursor);
        const mention = `@${user.first_name} `;
        const newValue = before + mention + after;
        onChange(newValue);
        setShowDropdown(false);
        setTriggerPos(null);

        setTimeout(() => {
            if (inputRef.current) {
                inputRef.current.focus();
                const pos = before.length + mention.length;
                inputRef.current.setSelectionRange(pos, pos);
            }
        }, 0);
    };

    const handleKeyDown = (e) => {
        if (!showDropdown || filtered.length === 0) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (onSubmit) {
                    onSubmit();
                } else {
                    // Fallback: blur to trigger onBlur save (used by DWL)
                    e.target.blur();
                }
                return;
            }
            if (e.key === 'Escape' && onCancel) {
                e.preventDefault();
                onCancel();
            }
            return;
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setSelectedIndex(prev => (prev + 1) % filtered.length);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setSelectedIndex(prev => (prev - 1 + filtered.length) % filtered.length);
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            e.preventDefault();
            insertMention(filtered[selectedIndex]);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            setShowDropdown(false);
        }
    };

    const defaultInputClass = "w-full px-2.5 py-1.5 text-xs border border-gray-300 dark:border-slate-500 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-accent-500 focus:border-transparent";
    const multilineExtras = " resize-none overflow-y-auto max-h-48";
    const resolvedClass = className || (multiline ? defaultInputClass + multilineExtras : defaultInputClass);

    const sharedProps = {
        ref: inputRef,
        value,
        onChange: handleChange,
        onKeyDown: handleKeyDown,
        onBlur,
        placeholder,
        disabled,
        className: resolvedClass,
    };

    return (
        <div className="flex-1">
            {multiline ? (
                <textarea {...sharedProps} rows={rows} />
            ) : (
                <input type="text" {...sharedProps} />
            )}

            {showDropdown && filtered.length > 0 && dropdownStyle && (
                <div
                    style={{ ...dropdownStyle, overflowY: 'auto' }}
                    className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-lg shadow-lg"
                >
                    {filtered.map((user, i) => (
                        <button
                            key={user.id}
                            type="button"
                            onMouseDown={(e) => { e.preventDefault(); insertMention(user); }}
                            className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                                i === selectedIndex
                                    ? 'bg-accent-50 dark:bg-accent-900/30 text-accent-700 dark:text-accent-300'
                                    : 'text-gray-700 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700'
                            }`}
                        >
                            <span className="font-medium">{user.first_name}</span>
                            {user.last_name && <span className="text-gray-400 dark:text-slate-500 ml-1">({user.last_name})</span>}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
});

export default MentionInput;
