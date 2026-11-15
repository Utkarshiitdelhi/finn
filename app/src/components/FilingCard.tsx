import { router } from 'expo-router';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import type { FeedCard, ResultRow } from '@/lib/api';
import { ago, C, catColor, F, num, pct, signColor, themed, tint } from '@/lib/theme';

import { Card, Chip, Mono, Serif, TierBadge } from './ui';

const METRIC: Record<string, string> = {
  revenue: 'Revenue', ebitda: 'EBITDA', pbt: 'PBT', pat: 'PAT', nii: 'NII', ppop: 'PPOP', gnpa_pct: 'Gross NPA %',
};

export function ResultsTable({ card }: { card: any }) {
  const rows: ResultRow[] = card?.rows || [];
  if (!rows.length) return null;
  return (
    <View style={st.table}>
      <View style={st.tr}>
        <Text style={[st.th, { flex: 1.3, textAlign: 'left' }]}>{card.period || 'Quarter'} · {card.unit}</Text>
        <Text style={st.th}>Qtr</Text>
        <Text style={st.th}>QoQ</Text>
        <Text style={st.th}>YoY</Text>
      </View>
      {rows.map((r) => (
        <View key={r.metric} style={st.tr}>
          <Text style={[st.td, { flex: 1.3, fontFamily: F.sans, color: C.sub, textAlign: 'left' }]}>
            {METRIC[r.metric] || r.metric}
            {r.derived ? <Text style={{ color: C.faint, fontSize: 10 }}> derived</Text> : null}
          </Text>
          <Mono style={st.td}>{num(r.q)}</Mono>
          <Mono style={[st.td, { color: signColor(r.qoq_pct) }]}>{pct(r.qoq_pct, 0)}</Mono>
          <Mono style={[st.td, { color: signColor(r.yoy_pct) }]}>{pct(r.yoy_pct, 0)}</Mono>
        </View>
      ))}
      {card.ebitda_margin ? (
        <Text style={st.foot}>
          EBITDA margin <Text style={{ fontFamily: F.mono, color: C.text }}>{card.ebitda_margin.q}%</Text> vs {card.ebitda_margin.pq ?? '—'}% last qtr, {card.ebitda_margin.yq ?? '—'}% a year ago
        </Text>
      ) : null}
      {card.verified === false ? <Chip small label="unverified: checks failed" color={C.tier.A} /> : null}
    </View>
  );
}

export function BioBlock({ card }: { card: any }) {
  const joined = card?.joined || [];
  const left = card?.left || [];
  if (!joined.length && !left.length) return null;
  return (
    <View style={{ gap: 6 }}>
      {left.map((p: any, i: number) => (
        <Text key={'l' + i} style={{ color: C.sub, fontSize: 13 }}>
          <Text style={{ color: C.down }}>Left </Text>
          {p.name} · {p.role}
        </Text>
      ))}
      {joined.map((p: any, i: number) => (
        <View key={'j' + i} style={{ gap: 2 }}>
          <Text style={{ color: C.sub, fontSize: 13 }}>
            <Text style={{ color: C.up }}>Joined </Text>
            {p.name} · {p.role}
            {p.effective_date ? ` · from ${p.effective_date}` : ''}
          </Text>
          <Text style={{ color: C.text, fontSize: 13, lineHeight: 19 }}>{p.bio || 'No profile in the filing.'}</Text>
        </View>
      ))}
    </View>
  );
}

export function PriceMove({ m }: { m: FeedCard['price_move'] }) {
  if (m?.pct === undefined || m?.pct === null) return null;
  return (
    <Text style={{ color: C.sub, fontSize: 13 }}>
      Stock <Mono style={{ color: signColor(m.pct) }}>{pct(m.pct)}</Mono>
      {m.vol_ratio ? (
        <>
          {' '}on <Mono>{m.vol_ratio.toFixed(1)}×</Mono> 20-day volume
        </>
      ) : null}{' '}
      the same day
    </Text>
  );
}

/** Card budget: one number that matters, shown big on the right. */
function keyNumber(f: FeedCard): { value: string; label: string; color: string } | null {
  const pat = f.card?.pat;
  if (f.category === 'results' && pat?.yoy_pct != null) return { value: pct(pat.yoy_pct, 0), label: 'PAT YoY', color: signColor(pat.yoy_pct) };
  if (f.price_move?.pct != null) return { value: pct(f.price_move.pct), label: 'stock today', color: signColor(f.price_move.pct) };
  if (f.card?.amount_cr) return { value: `₹${num(f.card.amount_cr)} cr`, label: 'size', color: C.text };
  return null;
}

export function FilingCard({ f, compact }: { f: FeedCard; compact?: boolean }) {
  const open = () => router.push(`/filing/${encodeURIComponent(f.id)}`);
  const cc = catColor(f.category);
  const k = keyNumber(f);
  const loud = f.tier === 'S' || f.tier === 'A';
  return (
    <Card onPress={compact ? open : undefined} accent={C.tier[f.tier]} tinted={loud}>
      <View style={st.meta}>
        <TierBadge tier={f.tier} />
        <Text style={st.ticker}>{f.ticker}</Text>
        <View style={[st.cat, { backgroundColor: tint(cc, 0.16) }]}>
          <View style={[st.catDot, { backgroundColor: cc }]} />
          <Text style={[st.catText, { color: cc }]}>{f.category_label}</Text>
        </View>
        <Text style={st.ago}>{ago(f.filed_at)} ago</Text>
      </View>
      <View style={st.headRow}>
        <Serif lines={compact ? 3 : undefined} style={[{ flex: 1 }, loud ? { fontSize: 18, lineHeight: 24, fontWeight: '600' } : null]}>
          {f.headline}
        </Serif>
        {k ? (
          <View style={[st.key, { backgroundColor: tint(k.color, 0.12) }]}>
            <Mono style={[st.keyVal, { color: k.color }]}>{k.value}</Mono>
            <Text style={st.keyLbl}>{k.label}</Text>
          </View>
        ) : null}
      </View>
      {f.summary && f.category !== 'results' ? (
        <Text style={st.summary} numberOfLines={compact ? 3 : undefined}>
          {f.summary}
        </Text>
      ) : null}
      {f.category === 'results' ? <ResultsTable card={f.card} /> : null}
      {f.category === 'management_change' ? <BioBlock card={f.card} /> : null}
      <PriceMove m={f.price_move} />
      {f.why?.length ? (
        <Text style={st.why}>
          <Text style={{ fontWeight: '700', color: C.tier[f.tier] }}>Why it's here: </Text>
          {f.why.join(' · ')}
        </Text>
      ) : null}
      <View style={st.actions}>
        <Pressable onPress={() => router.push(`/company/${f.ticker}`)} style={st.digBtn} hitSlop={6}>
          <Text style={st.digText}>Dig in →</Text>
        </Pressable>
        {f.source_url ? (
          <Pressable onPress={() => Linking.openURL(f.source_url)} hitSlop={8}>
            <Text style={st.srcLink}>Source filing ↗</Text>
          </Pressable>
        ) : null}
      </View>
    </Card>
  );
}

const st = themed(() => ({
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  ticker: { color: C.text, fontSize: 13, fontWeight: '800', fontFamily: F.mono, letterSpacing: 0.5 },
  cat: { flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 },
  catDot: { width: 6, height: 6, borderRadius: 3 },
  catText: { fontSize: 11, fontWeight: '700' },
  ago: { color: C.faint, fontSize: 11, marginLeft: 'auto' },
  headRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  key: { alignItems: 'flex-end', minWidth: 72, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 6 },
  keyVal: { fontSize: 20, fontWeight: '800' },
  keyLbl: { color: C.sub, fontSize: 9, letterSpacing: 0.6, textTransform: 'uppercase', fontWeight: '700' },
  why: { color: C.sub, fontSize: 12 },
  summary: { color: C.sub, fontSize: 14, lineHeight: 20 },
  actions: { flexDirection: 'row', gap: 16, marginTop: 2, alignItems: 'center' },
  digBtn: { backgroundColor: C.accent, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 7 },
  digText: { color: C.accentText, fontSize: 13, fontWeight: '700' },
  srcLink: { color: C.sub, fontSize: 13, fontWeight: '600' },
  table: { gap: 5, paddingVertical: 8, paddingHorizontal: 10, backgroundColor: C.surface2, borderRadius: 10 },
  tr: { flexDirection: 'row', alignItems: 'center' },
  th: { flex: 1, color: C.faint, fontSize: 11, textAlign: 'right' },
  td: { flex: 1, fontSize: 13, textAlign: 'right' },
  foot: { color: C.sub, fontSize: 12, marginTop: 4 },
}));
