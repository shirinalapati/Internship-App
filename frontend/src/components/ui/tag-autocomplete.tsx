import React, { useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';

interface TagAutocompleteProps {
  value: string[];
  onChange: (next: string[]) => void;
  suggestions: string[];
  placeholder?: string;
  disabled?: boolean;
  /** Allow adding free-text entries that aren't in the suggestion list. */
  allowCustom?: boolean;
  ariaLabel?: string;
}

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia focus-visible:ring-offset-2 focus-visible:ring-offset-bg';

/**
 * Multi-value tag input with type-ahead suggestions.
 *
 * - Selected values render as removable chips.
 * - Typing filters `suggestions`; click or Enter adds the highlighted match.
 * - With `allowCustom`, Enter on free text adds it verbatim (case preserved).
 * - Backspace on an empty input removes the last chip.
 */
const TagAutocomplete: React.FC<TagAutocompleteProps> = ({
  value,
  onChange,
  suggestions,
  placeholder,
  disabled,
  allowCustom = true,
  ariaLabel,
}) => {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const lowerSelected = useMemo(() => value.map(v => v.toLowerCase()), [value]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return suggestions
      .filter(s => !lowerSelected.includes(s.toLowerCase()))
      .filter(s => (q ? s.toLowerCase().includes(q) : true))
      .slice(0, 8);
  }, [suggestions, query, lowerSelected]);

  const addValue = (raw: string) => {
    const v = raw.trim();
    if (!v) return;
    if (lowerSelected.includes(v.toLowerCase())) {
      setQuery('');
      return;
    }
    onChange([...value, v]);
    setQuery('');
    setActiveIndex(0);
  };

  const removeAt = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setActiveIndex(i => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (open && filtered[activeIndex]) {
        addValue(filtered[activeIndex]);
      } else if (allowCustom) {
        addValue(query);
      } else if (filtered[0]) {
        addValue(filtered[0]);
      }
    } else if (e.key === 'Backspace' && !query && value.length) {
      removeAt(value.length - 1);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <div
        className={cn(
          'flex flex-wrap items-center gap-1.5 bg-bg border border-lp-border px-2 py-1.5 min-h-[2.5rem]',
          disabled && 'opacity-40'
        )}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((tag, idx) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 font-mono text-[11px] px-1.5 py-0.5 border border-ia bg-ia-subtle text-text-primary"
          >
            {tag}
            <button
              type="button"
              disabled={disabled}
              onClick={(e) => { e.stopPropagation(); removeAt(idx); }}
              className="hover:text-red-500 transition-colors"
              aria-label={`Remove ${tag}`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          aria-label={ariaLabel}
          value={query}
          disabled={disabled}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setActiveIndex(0); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={handleKeyDown}
          placeholder={value.length ? '' : placeholder}
          className={cn('flex-1 min-w-[8rem] bg-transparent text-sm text-text-primary placeholder:text-text-tertiary py-0.5 outline-none', focusRing)}
        />
      </div>

      {open && filtered.length > 0 && (
        <ul className="absolute z-20 mt-1 w-full max-h-56 overflow-auto bg-surface border border-lp-border shadow-lg">
          {filtered.map((s, i) => (
            <li key={s}>
              <button
                type="button"
                // onMouseDown (not onClick) so it fires before the input blur closes the list.
                onMouseDown={(e) => { e.preventDefault(); addValue(s); }}
                onMouseEnter={() => setActiveIndex(i)}
                className={cn(
                  'w-full text-left px-3 py-1.5 text-sm transition-colors',
                  i === activeIndex ? 'bg-ia-subtle text-text-primary' : 'text-text-secondary hover:bg-ia-subtle'
                )}
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default TagAutocomplete;
