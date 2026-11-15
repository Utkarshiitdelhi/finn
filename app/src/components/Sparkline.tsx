import { View } from 'react-native';

import { C } from '@/lib/theme';

/** Dependency-free sparkline: thin bars scaled to the range. Good enough for a 60-day price header. */
export function Sparkline({ values, height = 36, color }: { values: number[]; height?: number; color?: string }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const up = values[values.length - 1] >= values[0];
  const col = color || (up ? C.up : C.down);
  return (
    <View style={{ height, flexDirection: 'row', alignItems: 'flex-end', gap: 1 }}>
      {values.map((v, i) => (
        <View key={i} style={{ flex: 1, height: 2 + ((v - lo) / span) * (height - 2), backgroundColor: col, opacity: 0.35 + 0.65 * (i / values.length) }} />
      ))}
    </View>
  );
}

export function Bars({ values, height = 40 }: { values: (number | null)[]; height?: number }) {
  const v = values.map((x) => x ?? 0);
  const hi = Math.max(...v.map(Math.abs), 1);
  return (
    <View style={{ height, flexDirection: 'row', alignItems: 'flex-end', gap: 3 }}>
      {v.map((x, i) => (
        <View key={i} style={{ flex: 1, height: Math.max(2, (Math.abs(x) / hi) * height), backgroundColor: x >= 0 ? C.sub : C.down, borderRadius: 2, opacity: 0.5 + 0.5 * (i / v.length) }} />
      ))}
    </View>
  );
}
