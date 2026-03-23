'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';
import { searchEntities } from '@/lib/api';
import type { Entity } from '@/lib/types';
import { capitalize } from '@/lib/utils';
import clsx from 'clsx';

interface SearchBarProps {
  initialQuery?: string;
  size?: 'default' | 'large';
  className?: string;
}

export default function SearchBar({
  initialQuery = '',
  size = 'default',
  className,
}: SearchBarProps) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [suggestions, setSuggestions] = useState<Entity[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSuggestions([]);
      return;
    }
    try {
      const data = await searchEntities(q);
      setSuggestions(data.results.slice(0, 6));
    } catch {
      setSuggestions([]);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchSuggestions(query);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, fetchSuggestions]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/search?q=${encodeURIComponent(query.trim())}`);
      setShowSuggestions(false);
    }
  }

  function navigateToEntity(entity: Entity) {
    setShowSuggestions(false);
    if (entity.entity_type === 'person') {
      router.push(`/officials/${entity.slug}`);
    } else {
      router.push(`/entities/${entity.entity_type}/${entity.slug}`);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      navigateToEntity(suggestions[selectedIndex]);
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  }

  const isLarge = size === 'large';

  return (
    <div ref={wrapperRef} className={clsx('relative', className)}>
      <form onSubmit={handleSubmit}>
        <div
          className={clsx(
            'flex items-center gap-3 rounded-lg border border-zinc-700 bg-zinc-900 transition-colors focus-within:border-money-gold/50',
            isLarge ? 'px-5 py-4' : 'px-3 py-2'
          )}
        >
          <Search className={clsx('text-zinc-500', isLarge ? 'h-5 w-5' : 'h-4 w-4')} />
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setShowSuggestions(true);
              setSelectedIndex(-1);
            }}
            onFocus={() => setShowSuggestions(true)}
            onKeyDown={handleKeyDown}
            placeholder="Search officials, companies, bills, PACs..."
            className={clsx(
              'flex-1 border-none bg-transparent text-zinc-100 placeholder-zinc-500 outline-none',
              isLarge ? 'text-lg' : 'text-sm'
            )}
            aria-label="Search entities"
            aria-autocomplete="list"
            aria-expanded={showSuggestions && suggestions.length > 0}
          />
          <button
            type="submit"
            className={clsx(
              'rounded-md bg-money-gold font-semibold text-zinc-950 transition-colors hover:bg-money-gold-hover',
              isLarge ? 'px-6 py-2 text-sm' : 'px-3 py-1 text-xs'
            )}
          >
            Search
          </button>
        </div>
      </form>

      {/* Suggestions dropdown */}
      {showSuggestions && suggestions.length > 0 && (
        <ul
          className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl"
          role="listbox"
        >
          {suggestions.map((entity, index) => (
            <li
              key={entity.id}
              role="option"
              aria-selected={index === selectedIndex}
              className={clsx(
                'flex cursor-pointer items-center justify-between px-4 py-3 transition-colors',
                index === selectedIndex ? 'bg-zinc-800' : 'hover:bg-zinc-800/60'
              )}
              onMouseDown={() => navigateToEntity(entity)}
              onMouseEnter={() => setSelectedIndex(index)}
            >
              <span className="text-sm text-zinc-100">{entity.name}</span>
              <span className="rounded bg-zinc-700 px-2 py-0.5 text-xs text-zinc-400">
                {capitalize(entity.entity_type)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
