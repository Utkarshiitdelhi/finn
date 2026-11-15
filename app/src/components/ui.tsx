import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type StyleProp, type TextStyle, type ViewStyle } from 'react-native';

import { C, F } from '@/lib/theme';

export function Chip({ label, active, onPress, color, small }: { label: string; active?: boolean; onPress?: () => void; color?: string; small?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      style={[s.chip, small && s.chipSmall, active && { backgroundColor: C.text, borderColor: C.text }, color && { borderColor: color }]}>
      <Text style={[s.chipText, small && { fontSize: 11 }, active && { color: C.bg }, color && { color }]}>{label}</Text>
    </Pressable>
  );
}

export function TierBadge({ tier }: { tier: string }) {
  return (
    <View style={[s.badge, { backgroundColor: C.tier[tier] + '22', borderColor: C.tier[tier] }]}>
      <Text style={[s.badgeText, { color: C.tier[tier] }]}>{tier}</Text>
    </View>
  );
}

export function Mono({ children, style }: { children: ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[{ fontFamily: F.mono, color: C.text, fontVariant: ['tabular-nums'] }, style]}>{children}</Text>;
}

export function Serif({ children, style, lines }: { children: ReactNode; style?: StyleProp<TextStyle>; lines?: number }) {
  return (
    <Text numberOfLines={lines} style={[{ fontFamily: F.serif, color: C.text, fontSize: 17, lineHeight: 23 }, style]}>
      {children}
    </Text>
  );
}

export function Label({ children, style }: { children: ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[s.label, style]}>{children}</Text>;
}

export function Card({ children, style, onPress, accent }: { children: ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void; accent?: string }) {
  const body = <View style={[s.card, accent ? { borderLeftColor: accent, borderLeftWidth: 3 } : null, style]}>{children}</View>;
  return onPress ? (
    <Pressable onPress={onPress} style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}>
      {body}
    </Pressable>
  ) : (
    body
  );
}

export function Button({ label, onPress, kind = 'primary', small }: { label: string; onPress: () => void; kind?: 'primary' | 'ghost'; small?: boolean }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.btn, kind === 'ghost' && s.btnGhost, small && s.btnSmall, pressed && { opacity: 0.8 }]}>
      <Text style={[s.btnText, kind === 'ghost' && { color: C.text }, small && { fontSize: 13 }]}>{label}</Text>
    </Pressable>
  );
}

export function Loading({ label }: { label?: string }) {
  return (
    <View style={{ padding: 32, alignItems: 'center', gap: 12 }}>
      <ActivityIndicator color={C.sub} />
      {label ? <Text style={{ color: C.sub, fontSize: 13 }}>{label}</Text> : null}
    </View>
  );
}

export function Empty({ title, body }: { title: string; body?: string }) {
  return (
    <View style={{ padding: 28, alignItems: 'center', gap: 6 }}>
      <Serif style={{ color: C.sub }}>{title}</Serif>
      {body ? <Text style={{ color: C.faint, textAlign: 'center', fontSize: 13 }}>{body}</Text> : null}
    </View>
  );
}

export const s = StyleSheet.create({
  chip: { borderWidth: 1, borderColor: C.line, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  chipSmall: { paddingHorizontal: 8, paddingVertical: 3 },
  chipText: { color: C.sub, fontSize: 13, fontFamily: F.sans },
  badge: { borderWidth: 1, borderRadius: 4, width: 22, height: 22, alignItems: 'center', justifyContent: 'center' },
  badgeText: { fontFamily: F.mono, fontWeight: '700', fontSize: 12 },
  label: { color: C.faint, fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', fontFamily: F.sans },
  card: { backgroundColor: C.surface, borderRadius: 12, padding: 14, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line, gap: 8 },
  btn: { backgroundColor: C.text, borderRadius: 999, paddingVertical: 10, paddingHorizontal: 18, alignItems: 'center' },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: C.line },
  btnSmall: { paddingVertical: 6, paddingHorizontal: 12 },
  btnText: { color: C.bg, fontWeight: '600', fontSize: 14, fontFamily: F.sans },
});
