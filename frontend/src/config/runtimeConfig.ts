export interface SirixRuntimeConfig {
  /**
   * Resolved API origin without trailing slash.
   * Empty string ("") denotes same-origin relative `/api/*` requests
   * (canonical Single-Origin Google Cloud Run FastAPI + PWA deployment).
   */
  readonly apiBaseUrl: string;
  /** Human-readable backend origin for telemetry diagnostics & error banners. */
  readonly resolvedOriginDisplay: string;
  /** True when requests target the same origin serving the PWA shell. */
  readonly isSameOrigin: boolean;
  /**
   * Strictly gated sandbox/mock permission flag.
   * ALWAYS false by default (including all production builds).
   * Enabled ONLY when `VITE_ENABLE_SANDBOX=true` is explicitly configured.
   */
  readonly isSandboxAllowed: boolean;
  /** Vite build mode (`production`, `development`, etc.). */
  readonly mode: string;
}

function normalizeBaseUrl(rawValue: string | undefined): string {
  const trimmed = (rawValue ?? '').trim();
  if (!trimmed) {
    return '';
  }

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error(
      `Invalid VITE_API_URL / VITE_API_BASE_URL configuration: "${trimmed}". ` +
        'Expected a full https://<service>-<hash>-<region>.a.run.app origin or empty string for same-origin Cloud Run.'
    );
  }

  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    throw new Error(
      `Unsupported protocol "${parsed.protocol}" in VITE_API_URL. Only https:// or http:// origins are permitted.`
    );
  }

  return trimmed.replace(/\/+$/, '');
}

function resolveRuntimeConfig(): SirixRuntimeConfig {
  const env = import.meta.env;
  const rawApiUrl = env.VITE_API_URL || env.VITE_API_BASE_URL || '';
  const apiBaseUrl = normalizeBaseUrl(rawApiUrl);
  const isSameOrigin = apiBaseUrl.length === 0;
  const mode = env.MODE || 'production';

  // Zero silent sandbox fallback: sandbox mode is NEVER enabled implicitly.
  // Only an explicit build-time `VITE_ENABLE_SANDBOX=true` unlocks manual sandbox preview.
  const isSandboxAllowed = String(env.VITE_ENABLE_SANDBOX ?? '').trim().toLowerCase() === 'true';

  const currentOrigin =
    typeof window !== 'undefined' && window.location?.origin ? window.location.origin : 'same-origin';

  return {
    apiBaseUrl,
    resolvedOriginDisplay: isSameOrigin ? `${currentOrigin} (same-origin)` : apiBaseUrl,
    isSameOrigin,
    isSandboxAllowed,
    mode,
  };
}

export const RUNTIME_CONFIG: SirixRuntimeConfig = resolveRuntimeConfig();

export function buildApiUrl(path: string, forceBust = false): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const base = `${RUNTIME_CONFIG.apiBaseUrl}${normalizedPath}`;
  if (!forceBust) {
    return base;
  }
  const separator = normalizedPath.includes('?') ? '&' : '?';
  return `${base}${separator}t=${Date.now()}`;
}
