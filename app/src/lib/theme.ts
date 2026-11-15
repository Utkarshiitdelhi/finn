import { Platform, StyleSheet } from 'react-native';

// Two palettes, one mutable `C`: switching theme copies a palette into C and remounts the tree,
// so every `C.x` read and every `themed()` style picks up the new colours.
type Palette = {
  bg: string; surface: string; surface2: string; line: string; text: string; sub: string; faint: string;
  up: string; down: string; accent: string; accentText: string; tier: Record<string, string>; mode: 'dark' | 'light';
};

const DARK: Palette = {
  mode: 'dark',
  bg: '#050507',
  surface: '#0F1115',
  surface2: '#171A20',
  line: '#252A33',
  text: '#F3F5F8',
  sub: '#A7B0BD',
  faint: '#6B7482',
  up: '#34D399',
  down: '#FF5A5F',
  accent: '#6C8CFF',
  accentText: '#FFFFFF',
  tier: { S: '#FF4D57', A: '#FFB020', B: '#8B95A5', C: '#5E6773' },
};

const LIGHT: Palette = {
  mode: 'light',
  bg: '#F5F6F8',
  surface: '#FFFFFF',
  surface2: '#EEF0F4',
  line: '#E2E5EA',
  text: '#0B0D12',
  sub: '#4B5563',
  faint: '#8A93A0',
  up: '#16A34A',
  down: '#DC2626',
  accent: '#2F5BEA',
  accentText: '#FFFFFF',
  tier: { S: '#E11D2E', A: '#D97706', B: '#64748B', C: '#94A3B8' },
};

export const C: Palette = { ...DARK, tier: { ...DARK.tier } };
let version = 0;

export function applyTheme(mode: 'dark' | 'light') {
  if (C.mode === mode && version > 0) return;
  const p = mode === 'light' ? LIGHT : DARK;
  Object.assign(C, p, { tier: { ...p.tier } });
  version++;
}

/** StyleSheet-like object whose values are recomputed after a theme switch. */
type Styles = Parameters<typeof StyleSheet.create>[0];
export function themed<T extends Styles>(fn: () => T & Styles): Readonly<T> {
  let seen = -1;
  let cache: T = {} as T;
  return new Proxy({} as Readonly<T>, {
    get(_t, key: string) {
      if (seen !== version) {
        cache = fn();
        seen = version;
      }
      return cache[key];
    },
  });
}

/** Colour at low opacity, for tinted card backgrounds. */
export const tint = (hex: string, alpha = 0.12) =>
  hex + Math.round(alpha * 255).toString(16).padStart(2, '0');

export const TIER_WORD: Record<string, string> = { S: 'URGENT', A: 'WORTH A LOOK', B: 'FYI', C: 'ROUTINE' };

// One hue per filing category, so the eye can sort the feed before reading it.
const CAT: Record<string, string> = {
  results: '#4F8CFF', management_change: '#A78BFA', credit_rating: '#F472B6', 'M&A': '#22D3EE',
  pledging: '#FB923C', litigation: '#F87171', fund_raise: '#2DD4BF', insider_trading: '#FBBF24',
  capex: '#84CC16', press_release: '#94A3B8', dividend: '#34D399', bonus_split: '#34D399',
  earnings_call: '#60A5FA', board_meeting: '#94A3B8',
};
export const catColor = (cat: string) => CAT[cat] || C.faint;

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
