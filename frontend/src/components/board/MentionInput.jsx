/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides a text input with @mention autocomplete dropdown so users can tag teammates in board comments.
 * exports:
 *   MentionInput: Controlled input that detects @-triggers, shows a filtered user dropdown, and inserts mention tokens
 * imports_from: [react]
 * imported_by: [components/board/BoardDetail.jsx]
 * invariants:
 *   - Enter submits the form when the dropdown is closed; when open it selects the highlighted user
 *   - Dropdown renders above the input (bottom-full) to avoid clipping in pinned-bottom comment areas
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useRef, useEffect } from 'react';

export default function MentionInput({ value, onChange, onSubmit, users, placeholder, disabled }) {
    const [showDropdown, setShowDropdown] = useState(false);
    const [filterText, setFilterText] = useState('');
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [triggerPos, setTriggerPos] = useState(null);
    const inputRef = useRef(null);

    const filtered = users.filter(u => {
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

        // Check if we're in a mention context
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

        // Restore focus and cursor position
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
                onSubmit();
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
            setShowDropdown(false);
        }
    };

    return (
        <div className="relative flex-1">
            <input
                ref={inputRef}
                type="text"
                value={value}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
                placeholder={placeholder}
                disabled={disabled}
                className="w-full px-2.5 py-1.5 text-xs border border-gray-300 dark:border-slate-500 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-accent-500 focus:border-transparent"
            />

            {showDropdown && filtered.length > 0 && (
                <div className="absolute bottom-full mb-1 left-0 w-full max-h-36 overflow-y-auto bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-lg shadow-lg z-50">
                    {filtered.map((user, i) => (
                        <button
                            key={user.id}
                            type="button"
                            onMouseDown={(e) => { e.preventDefault(); insertMention(user); }}
                            className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
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
}
