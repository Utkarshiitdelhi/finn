import { Platform } from 'react-native';

// Dark by default; editorial serif for headlines; monospace tabular figures for every number;
// one accent per tier; green/red reserved for up/down only.
export const C = {
  bg: '#0B0D10',
  surface: '#14171C',
  surface2: '#1B1F26',
  line: '#262B33',
  text: '#ECEEF1',
  sub: '#9AA3AE',
  faint: '#5E6773',
  up: '#30A46C',
  down: '#E5484D',
  accent: '#7C9CFF',
  tier: { S: '#E5484D', A: '#F5A524', B: '#9AA3AE', C: '#5E6773' } as Record<string, string>,
};

export const F = {
  serif: Platform.select({ ios: 'Georgia', android: 'serif', default: 'Georgia, "Times New Roman", serif' }),
  mono: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'ui-monospace, Menlo, monospace' }),
  sans: Platform.select({ ios: 'System', android: 'sans-serif', default: 'system-ui, -apple-system, sans-serif' }),
};

export const num = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : v.toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(digits)}%`;

export const signColor = (v: number | null | undefined) => (v === null || v === undefined ? C.sub : v >= 0 ? C.up : C.down);

export const ago = (iso: string) => {
  const t = new Date(iso.endsWith('Z') ? iso : iso + 'Z').getTime();
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (m < 60) return `${m}m`;
  if (m < 60 * 24) return `${Math.round(m / 60)}h`;
  return `${Math.round(m / 1440)}d`;
};
