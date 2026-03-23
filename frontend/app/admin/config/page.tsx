'use client';

import { useState, useEffect, useCallback } from 'react';
import { getConfig, setConfigValue, clearConfigValue } from '@/lib/api';
import type { ConfigEntry } from '@/lib/types';
import LoadingState from '@/components/LoadingState';
import { Settings, CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import clsx from 'clsx';

export default function AdminConfigPage() {
  const [configs, setConfigs] = useState<ConfigEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getConfig();
      setConfigs(data);
    } catch {
      setError('Failed to load configuration. Please try again later.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  async function handleSave(key: string) {
    setSaving(true);
    try {
      await setConfigValue(key, editValue);
      setEditingKey(null);
      setEditValue('');
      await fetchConfig();
    } catch {
      setError(`Failed to save ${key}.`);
    } finally {
      setSaving(false);
    }
  }

  async function handleClear(key: string) {
    setSaving(true);
    try {
      await clearConfigValue(key);
      await fetchConfig();
    } catch {
      setError(`Failed to clear ${key}.`);
    } finally {
      setSaving(false);
    }
  }

  function sourceLabel(source: string): string {
    switch (source) {
      case 'database':
        return 'DB';
      case 'env_var':
        return 'ENV';
      case 'default':
        return 'Default';
      default:
        return 'Not Set';
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Settings className="h-6 w-6 text-money-gold" />
          <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
            Configuration
          </h1>
        </div>
        <p className="mt-2 text-sm text-zinc-500">
          Manage API keys and application settings
        </p>
      </div>

      {/* Content */}
      {loading && <LoadingState variant="card" count={4} />}

      {error && (
        <div className="mb-6 rounded-lg border border-red-500/20 bg-red-500/5 p-4">
          <p className="text-sm text-red-300">{error}</p>
          <button
            onClick={() => { setError(null); fetchConfig(); }}
            className="mt-2 rounded-md bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Try Again
          </button>
        </div>
      )}

      {!loading && !error && configs.length === 0 && (
        <div className="rounded-lg border border-zinc-800 bg-money-surface p-12 text-center">
          <Settings className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-500">
            No configuration items found.
          </p>
        </div>
      )}

      {!loading && configs.length > 0 && (
        <div className="space-y-3">
          {configs.map((cfg) => (
            <div
              key={cfg.key}
              className="rounded-lg border border-zinc-800 bg-money-surface p-5"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-mono text-sm font-semibold text-zinc-100">
                      {cfg.key}
                    </h3>
                    {cfg.is_configured ? (
                      <CheckCircle className="h-4 w-4 text-green-400" />
                    ) : (
                      <XCircle className="h-4 w-4 text-zinc-600" />
                    )}
                    <span
                      className={clsx(
                        'rounded px-1.5 py-0.5 text-xs font-medium',
                        cfg.source === 'database'
                          ? 'bg-blue-500/20 text-blue-400'
                          : cfg.source === 'env_var'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : cfg.source === 'default'
                              ? 'bg-zinc-700/50 text-zinc-400'
                              : 'bg-zinc-800 text-zinc-500'
                      )}
                    >
                      {sourceLabel(cfg.source)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-zinc-400">{cfg.description}</p>
                  {cfg.masked_value && (
                    <p className="mt-1 font-mono text-xs text-zinc-500">
                      {cfg.masked_value}
                    </p>
                  )}
                </div>

                <div className="flex shrink-0 gap-2">
                  {editingKey === cfg.key ? (
                    <>
                      <input
                        type={cfg.is_secret ? 'password' : 'text'}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        placeholder="Enter value..."
                        className="w-48 rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-money-gold"
                        autoFocus
                      />
                      <button
                        onClick={() => handleSave(cfg.key)}
                        disabled={saving || !editValue.trim()}
                        className="rounded bg-money-gold px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-money-gold-hover disabled:opacity-50"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => { setEditingKey(null); setEditValue(''); }}
                        className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:border-zinc-600"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => { setEditingKey(cfg.key); setEditValue(''); }}
                        className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                      >
                        Edit
                      </button>
                      {cfg.is_configured && cfg.source === 'database' && (
                        <button
                          onClick={() => handleClear(cfg.key)}
                          disabled={saving}
                          className="rounded border border-red-500/30 px-3 py-1.5 text-xs text-red-400 hover:border-red-500/50 hover:text-red-300 disabled:opacity-50"
                        >
                          Clear
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Refresh button */}
          <div className="pt-4">
            <button
              onClick={fetchConfig}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
