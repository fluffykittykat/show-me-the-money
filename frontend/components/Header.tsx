'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, useEffect } from 'react';
import { Search, Menu, X, Settings, Bell } from 'lucide-react';
import { getUnreadAlertCount } from '@/lib/api';

export default function Header() {
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [unreadAlerts, setUnreadAlerts] = useState(0);

  useEffect(() => {
    const fetchCount = () => {
      getUnreadAlertCount().then((d) => setUnreadAlerts(d.count)).catch(() => {});
    };
    fetchCount();
    const interval = setInterval(fetchCount, 60000);
    return () => clearInterval(interval);
  }, []);

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
      setSearchOpen(false);
      setSearchQuery('');
    }
  }

  return (
    <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Wordmark */}
        <Link href="/" className="flex items-baseline gap-1 text-lg font-bold tracking-widest">
          <span className="text-zinc-100">FOLLOW THE</span>
          <span className="text-money-gold">MONEY</span>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden items-center gap-8 md:flex" aria-label="Main navigation">
          <Link
            href="/"
            className="text-sm font-medium text-zinc-400 transition-colors hover:text-zinc-100"
          >
            Home
          </Link>
          <Link
            href="/officials"
            className="text-sm font-medium text-zinc-400 transition-colors hover:text-zinc-100"
          >
            Officials
          </Link>
          <Link
            href="/trades"
            className="text-sm font-medium text-zinc-400 transition-colors hover:text-zinc-100"
          >
            Trades
          </Link>
          <Link
            href="/alerts"
            className="relative text-sm font-medium text-zinc-400 transition-colors hover:text-zinc-100"
          >
            <span className="flex items-center gap-1">
              <Bell className="h-3.5 w-3.5" />
              Alerts
            </span>
            {unreadAlerts > 0 && (
              <span className="absolute -right-3 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                {unreadAlerts > 99 ? '99+' : unreadAlerts}
              </span>
            )}
          </Link>
          <Link
            href="/search"
            className="text-sm font-medium text-zinc-400 transition-colors hover:text-zinc-100"
          >
            Search
          </Link>
          <Link
            href="/admin/config"
            className="text-sm font-medium text-zinc-400 transition-colors hover:text-zinc-100"
            aria-label="Admin settings"
          >
            <Settings className="h-4 w-4" />
          </Link>

          {/* Search toggle */}
          <button
            onClick={() => setSearchOpen(!searchOpen)}
            className="rounded-md p-2 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            aria-label="Toggle search"
          >
            <Search className="h-4 w-4" />
          </button>
        </nav>

        {/* Mobile menu button */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="rounded-md p-2 text-zinc-400 md:hidden"
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Search bar (desktop) */}
      {searchOpen && (
        <div className="hidden border-t border-zinc-800 bg-zinc-950/95 px-4 py-3 md:block">
          <form onSubmit={handleSearchSubmit} className="mx-auto max-w-2xl">
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 text-zinc-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search officials, companies, bills..."
                className="flex-1 border-none bg-transparent text-sm text-zinc-100 placeholder-zinc-500 outline-none"
                autoFocus
              />
              <button
                type="submit"
                className="rounded bg-money-gold px-3 py-1 text-xs font-semibold text-zinc-950 transition-colors hover:bg-money-gold-hover"
              >
                Search
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Mobile menu */}
      {mobileMenuOpen && (
        <nav
          className="border-t border-zinc-800 bg-zinc-950/95 px-4 py-4 md:hidden"
          aria-label="Mobile navigation"
        >
          <div className="flex flex-col gap-3">
            <Link
              href="/"
              onClick={() => setMobileMenuOpen(false)}
              className="text-sm font-medium text-zinc-300"
            >
              Home
            </Link>
            <Link
              href="/officials"
              onClick={() => setMobileMenuOpen(false)}
              className="text-sm font-medium text-zinc-300"
            >
              Officials
            </Link>
            <Link
              href="/trades"
              onClick={() => setMobileMenuOpen(false)}
              className="text-sm font-medium text-zinc-300"
            >
              Trades
            </Link>
            <Link
              href="/alerts"
              onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-2 text-sm font-medium text-zinc-300"
            >
              Alerts
              {unreadAlerts > 0 && (
                <span className="rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                  {unreadAlerts}
                </span>
              )}
            </Link>
            <Link
              href="/admin/config"
              onClick={() => setMobileMenuOpen(false)}
              className="text-sm font-medium text-zinc-300"
            >
              Admin
            </Link>
            <form onSubmit={handleSearchSubmit} className="mt-2">
              <div className="flex items-center gap-2 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2">
                <Search className="h-4 w-4 text-zinc-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search..."
                  className="flex-1 border-none bg-transparent text-sm text-zinc-100 placeholder-zinc-500 outline-none"
                />
              </div>
            </form>
          </div>
        </nav>
      )}
    </header>
  );
}
