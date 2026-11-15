import { router } from 'expo-router';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import type { FeedCard, ResultRow } from '@/lib/api';
import { ago, C, F, num, pct, signColor } from '@/lib/theme';

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
        <Text style={[st.th, { flex: 1.3 }]}>{card.period || 'Quarter'} · {card.unit}</Text>
        <Text style={st.th}>Qtr</Text>
        <Text style={st.th}>QoQ</Text>
        <Text style={st.th}>YoY</Text>
      </View>
      {rows.map((r) => (
        <View key={r.metric} style={st.tr}>
          <Text style={[st.td, { flex: 1.3, fontFamily: F.sans, color: C.sub }]}>
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

export function FilingCard({ f, compact }: { f: FeedCard; compact?: boolean }) {
  const open = () => router.push(`/filing/${encodeURIComponent(f.id)}`);
  return (
    <Card onPress={compact ? open : undefined} accent={C.tier[f.tier]}>
      <View style={st.meta}>
        <TierBadge tier={f.tier} />
        <Text style={st.metaText}>
          {f.ticker} · {f.category_label} · {ago(f.filed_at)}
        </Text>
        {f.why?.length ? <Text style={st.why}>why {f.tier}? {f.why.join(' · ')}</Text> : null}
      </View>
      <Serif lines={compact ? 2 : undefined}>{f.headline}</Serif>
      {f.summary && f.category !== 'results' ? (
        <Text style={st.summary} numberOfLines={compact ? 3 : undefined}>
          {f.summary}
        </Text>
      ) : null}
      {f.category === 'results' ? <ResultsTable card={f.card} /> : null}
      {f.category === 'management_change' ? <BioBlock card={f.card} /> : null}
      <PriceMove m={f.price_move} />
      <View style={st.actions}>
        <Pressable onPress={() => router.push(`/company/${f.ticker}`)} hitSlop={8}>
          <Text style={st.action}>Dig in →</Text>
        </Pressable>
        {f.source_url ? (
          <Pressable onPress={() => Linking.openURL(f.source_url)} hitSlop={8}>
            <Text style={[st.action, { color: C.sub }]}>Source filing</Text>
          </Pressable>
        ) : null}
      </View>
    </Card>
  );
}

const st = StyleSheet.create({
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  metaText: { color: C.sub, fontSize: 12, fontFamily: F.mono },
  why: { color: C.faint, fontSize: 11, marginLeft: 'auto' },
  summary: { color: C.sub, fontSize: 14, lineHeight: 20 },
  actions: { flexDirection: 'row', gap: 18, marginTop: 2 },
  action: { color: C.accent, fontSize: 13, fontWeight: '600' },
  table: { gap: 4, paddingVertical: 4 },
  tr: { flexDirection: 'row', alignItems: 'center' },
  th: { flex: 1, color: C.faint, fontSize: 11, textAlign: 'right' },
  td: { flex: 1, fontSize: 13, textAlign: 'right' },
  foot: { color: C.sub, fontSize: 12, marginTop: 4 },
});
