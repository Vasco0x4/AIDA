import { utcDate } from '../../utils/utcDate';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Calendar,
  Clock,
  ExternalLink,
  RefreshCw,
  ShieldAlert,
} from '../icons';
import { useAuth } from '../../contexts/AuthContext';
import apiClient from '../../services/api';
import { createNvdService } from '../../services/nvdService';

const nvdService = createNvdService(apiClient);
const MAX_COMPACT_ITEMS = 8;

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
});

function parseDate(value) {
  if (!value) return null;
  const date = utcDate(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value) {
  const date = parseDate(value);
  return date ? dateTimeFormatter.format(date) : 'Not available';
}

function formatDate(value) {
  const date = parseDate(value);
  return date ? dateFormatter.format(date) : 'Not available';
}

function formatCacheAge(seconds) {
  if (!Number.isFinite(seconds)) return 'Not available';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function getErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (typeof error?.message === 'string' && error.message.trim()) return error.message;
  return fallback;
}

const NVDDigest = () => {
  const { user } = useAuth();
  const [digest, setDigest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [requestError, setRequestError] = useState(null);
  const [announcement, setAnnouncement] = useState('');
  const mounted = useRef(false);
  const requestId = useRef(0);

  const canRefresh = user?.role === 'admin';

  const loadDigest = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setRequestError(null);

    try {
      const data = await nvdService.getDigest();
      if (mounted.current && currentRequest === requestId.current) {
        setDigest(data);
      }
    } catch (error) {
      if (mounted.current && currentRequest === requestId.current) {
        setRequestError(getErrorMessage(error, 'Unable to load the NVD digest.'));
      }
    } finally {
      if (mounted.current && currentRequest === requestId.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    loadDigest();

    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, [loadDigest]);

  const handleRefresh = async () => {
    if (!canRefresh || refreshing || loading) return;

    setRefreshing(true);
    setRequestError(null);
    setAnnouncement('');

    try {
      const data = await nvdService.refresh();
      if (!mounted.current) return;
      setDigest(data);
      setAnnouncement(
        data.error
          ? 'NVD refresh failed. Cached results are shown when available.'
          : 'NVD digest refreshed.'
      );
    } catch (error) {
      if (!mounted.current) return;
      const message = error?.response?.status === 403
        ? 'Administrator access is required to refresh the NVD cache.'
        : getErrorMessage(error, 'Unable to refresh the NVD digest.');
      setRequestError(message);
      setAnnouncement('NVD refresh failed. Cached results are shown when available.');
    } finally {
      if (mounted.current) setRefreshing(false);
    }
  };

  const items = Array.isArray(digest?.items) ? digest.items : [];
  const itemCount = Number.isFinite(digest?.item_count) ? digest.item_count : items.length;
  const stale = digest ? digest.stale || digest.status !== 'fresh' : false;
  const busy = loading || refreshing;

  return (
    <section
      aria-labelledby="nvd-digest-title"
      aria-busy={busy}
      className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg p-5"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 p-2 bg-red-50 dark:bg-red-900/20 rounded-md">
            <ShieldAlert className="w-4 h-4 text-red-600 dark:text-red-400" aria-hidden="true" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="nvd-digest-title" className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                NVD Critical CVE Digest
              </h2>
              {digest && (
                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                  stale
                    ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
                    : 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${stale ? 'bg-amber-500' : 'bg-green-500'}`} aria-hidden="true" />
                  {stale ? 'Stale cache' : 'Fresh cache'}
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              Cached critical vulnerabilities from the National Vulnerability Database
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleRefresh}
          disabled={!canRefresh || busy}
          aria-describedby={!canRefresh ? 'nvd-refresh-help' : undefined}
          className="inline-flex items-center justify-center gap-1.5 self-start px-3 py-1.5 text-xs font-medium text-neutral-700 dark:text-neutral-300 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>

      {digest && (
        <dl className="grid grid-cols-2 lg:grid-cols-4 gap-x-4 gap-y-3 mt-4 py-3 border-y border-neutral-100 dark:border-neutral-700">
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">Cached items</dt>
            <dd className="mt-0.5 text-xs font-medium text-neutral-800 dark:text-neutral-200">
              {itemCount.toLocaleString()} in {digest.lookback_days ?? '—'}-day window
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">Publication window</dt>
            <dd className="mt-0.5 text-xs font-medium text-neutral-800 dark:text-neutral-200">
              {digest.window_start ? `${formatDate(digest.window_start)} – ${formatDate(digest.window_end)}` : 'No cached window'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">Last successful refresh</dt>
            <dd className="mt-0.5 text-xs font-medium text-neutral-800 dark:text-neutral-200">
              {digest.last_success_at ? `${formatCacheAge(digest.cache_age_seconds)} · ${formatDateTime(digest.last_success_at)}` : 'Never'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">Schedule</dt>
            <dd className="mt-0.5 text-xs font-medium text-neutral-800 dark:text-neutral-200">
              {digest.enabled
                ? `Every ${digest.refresh_interval_hours ?? '—'}h${digest.next_refresh_at ? ` · Next ${formatDateTime(digest.next_refresh_at)}` : ''}`
                : 'Automatic refresh disabled'}
            </dd>
          </div>
        </dl>
      )}

      {(digest?.error || requestError) && (
        <div
          role="alert"
          className="mt-4 flex items-start gap-2 rounded-md border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 px-3 py-2.5"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0 text-red-600 dark:text-red-400" aria-hidden="true" />
          <div className="min-w-0 text-xs">
            <p className="font-medium text-red-800 dark:text-red-300">
              {requestError ? 'Unable to update the NVD digest' : 'Last NVD refresh failed'}
            </p>
            <p className="mt-0.5 break-words text-red-700 dark:text-red-400">
              {requestError || digest.error}
            </p>
            {digest && <p className="mt-1 text-red-700 dark:text-red-400">Cached results are shown when available.</p>}
            {!digest && (
              <button
                type="button"
                onClick={loadDigest}
                disabled={loading}
                className="mt-2 inline-flex items-center gap-1 font-medium text-red-800 dark:text-red-300 hover:underline disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
              >
                <RefreshCw className="w-3 h-3" aria-hidden="true" />
                Retry loading
              </button>
            )}
          </div>
        </div>
      )}

      {loading && !digest ? (
        <div role="status" className="flex items-center justify-center gap-2 py-10 text-sm text-neutral-500 dark:text-neutral-400">
          <RefreshCw className="w-4 h-4 animate-spin" aria-hidden="true" />
          Loading cached NVD digest…
        </div>
      ) : digest && items.length > 0 ? (
        <>
          <ul aria-label="Cached critical CVEs" className="divide-y divide-neutral-100 dark:divide-neutral-700">
            {items.slice(0, MAX_COMPACT_ITEMS).map((item) => (
              <li key={item.cve_id} className="py-3 first:pt-4 last:pb-0">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <a
                      href={item.nvd_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`View ${item.cve_id} on NVD (opens in a new tab)`}
                      className="inline-flex items-center gap-1 text-sm font-semibold font-mono text-primary-700 dark:text-primary-400 hover:underline focus:outline-none focus:ring-2 focus:ring-primary-500 rounded"
                    >
                      {item.cve_id}
                      <ExternalLink className="w-3 h-3" aria-hidden="true" />
                    </a>
                    <p className="mt-1 text-xs leading-5 text-neutral-600 dark:text-neutral-400 line-clamp-2">
                      {item.description || 'No description provided.'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="inline-flex px-2 py-0.5 rounded text-[11px] font-semibold bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                      {(item.cvss_severity || 'CRITICAL').toUpperCase()}
                    </span>
                    <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300 whitespace-nowrap">
                      CVSS {item.cvss_version ? `${item.cvss_version} · ` : ''}{item.cvss_score ?? 'N/A'}
                    </span>
                  </div>
                </div>
                <div className="mt-1.5 flex items-center gap-1 text-[11px] text-neutral-500 dark:text-neutral-400">
                  <Calendar className="w-3 h-3" aria-hidden="true" />
                  Published{' '}
                  <time dateTime={item.published_at}>{formatDateTime(item.published_at)}</time>
                </div>
                {(item.affected_products || []).length > 0 && (
                  <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400 break-words">
                    Affected: {item.affected_products.slice(0, 2).join('; ')}
                    {item.affected_products.length > 2 ? ` (+${item.affected_products.length - 2} more)` : ''}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {itemCount > MAX_COMPACT_ITEMS && (
            <p className="mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-700 text-[11px] text-neutral-500 dark:text-neutral-400">
              Showing the latest {Math.min(items.length, MAX_COMPACT_ITEMS)} of {itemCount.toLocaleString()} cached items.
            </p>
          )}
        </>
      ) : digest ? (
        <div role="status" className="py-8 text-center">
          <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-neutral-300 dark:text-neutral-600" aria-hidden="true" />
          <p className="text-sm font-medium text-neutral-600 dark:text-neutral-300">No critical CVEs in this cache window</p>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {digest.last_success_at ? 'The latest refresh returned no matching vulnerabilities.' : 'Refresh the cache to retrieve vulnerabilities from NVD.'}
          </p>
        </div>
      ) : !loading && !requestError ? (
        <div role="status" className="py-8 text-center text-sm text-neutral-500 dark:text-neutral-400">
          No NVD digest is available.
        </div>
      ) : null}

      {!canRefresh && (
        <p id="nvd-refresh-help" className="mt-3 flex items-center gap-1 text-[11px] text-neutral-500 dark:text-neutral-400">
          <Clock className="w-3 h-3" aria-hidden="true" />
          Manual refresh requires an administrator.
        </p>
      )}
    </section>
  );
};

export default NVDDigest;
