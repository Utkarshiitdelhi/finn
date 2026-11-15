import { router } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { FilingCard } from '@/components/FilingCard';
import { Chip, Empty, Label, Loading, Serif } from '@/components/ui';
import { api, type Feed, type FeedCard } from '@/lib/api';
import { useFinn, useScreen } from '@/lib/finnContext';
import { C, F, themed, tint } from '@/lib/theme';

const WINDOWS = [
  { key: '24h', label: '24 h' },
  { key: '3d', label: '3 d' },
  { key: '7d', label: '7 d' },
  { key: '30d', label: '30 d' },
];

export default function FeedScreen() {
  useScreen({ screen: 'feed' });
  const { bump } = useFinn();
  const [win, setWin] = useState('24h');
  const [data, setData] = useState<Feed | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [bySector, setBySector] = useState(false);
  const [showC, setShowC] = useState(false);
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<{ ticker: string; name: string; held: boolean }[]>([]);

  const [widened, setWidened] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      let d = await api.feed(win);
      // Quiet day: widen 24 h → 7 d → 30 d once, and say so, instead of showing an empty feed.
      if (!widened && d.counts.S === 0) {
        for (const w of ['7d', '30d'].filter((x) => x !== win)) {
          const wider = await api.feed(w);
          if (wider.counts.S > 0) {
            setWidened(`Nothing urgent in the last ${WINDOWS.find((x) => x.key === win)?.label}, so showing ${WINDOWS.find((x) => x.key === w)?.label}.`);
            setWin(w);
            d = wider;
            break;
          }
        }
      }
      setData(d);
    } catch (e: any) {
      setErr(e.name === 'AbortError' ? 'Server is waking up (free tier). Pull to retry.' : e.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [win]);

  useEffect(() => {
    load();
  }, [load, bump]);

  useEffect(() => {
    if (q.trim().length < 2) return setHits([]);
    const t = setTimeout(() => api.search(q).then(setHits).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [q]);

  const dismiss = async (f: FeedCard) => {
    await api.filingAction(f.id, 'dismiss').catch(() => {});
    load();
  };

  const sections = useMemo(() => {
    if (!data) return [];
    if (!bySector) return (['S', 'A', 'B'] as const).map((t) => ({ key: t, title: { S: 'Needs you now', A: 'Worth a look', B: 'For the record' }[t], items: data[t] }));
    const groups: Record<string, FeedCard[]> = {};
    [...data.S, ...data.A, ...data.B].forEach((f) => (groups[f.sector || 'Other'] ||= []).push(f));
    return Object.entries(groups).map(([k, items]) => ({ key: k, title: k, items }));
  }, [data, bySector]);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={st.page} refreshControl={<RefreshControl refreshing={loading && !!data} onRefresh={load} tintColor={C.sub} />}>
      {data ? (
        <View style={st.hero}>
          <Text style={st.heroDate}>
            {new Date().toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }).toUpperCase()} · YOUR BRIEF
          </Text>
          <Serif style={st.heroLine}>
            {data.counts.S + data.counts.A > 0 ? (
              <>
                <Text style={{ color: C.tier.S }}>{data.counts.S + data.counts.A}</Text>
                {` thing${data.counts.S + data.counts.A === 1 ? '' : 's'} need${data.counts.S + data.counts.A === 1 ? 's' : ''} you.`}
              </>
            ) : (
              'Nothing needs you right now.'
            )}
          </Serif>
          <View style={st.counters}>
            {(
              [
                ['S', 'urgent'],
                ['A', 'worth a look'],
                ['B', 'for the record'],
              ] as const
            ).map(([t, label]) => (
              <View key={t} style={[st.pill, { backgroundColor: tint(C.tier[t], 0.14), borderColor: tint(C.tier[t], 0.4) }]}>
                <Text style={[st.pillNum, { color: C.tier[t] }]}>{data.counts[t]}</Text>
                <Text style={[st.pillLbl, { color: C.tier[t] }]}>{label}</Text>
              </View>
            ))}
            <View style={[st.pill, { borderColor: C.line }]}>
              <Text style={[st.pillNum, { color: C.faint }]}>{data.C.count}</Text>
              <Text style={[st.pillLbl, { color: C.faint }]}>routine, hidden</Text>
            </View>
          </View>
          <Text style={st.explain}>
            FINN reads every NSE filing for your holdings and ranks it by how much it matters to you. Tap a card for the full story,{' '}
            <Text style={{ color: C.accent, fontWeight: '700' }}>Dig in</Text> for research, or hold{' '}
            <Text style={{ color: C.accent, fontWeight: '700' }}>Ask FINN</Text> to talk.
          </Text>
          {widened && widened !== 'x' ? <Text style={st.widened}>{widened}</Text> : null}
        </View>
      ) : null}

      <TextInput value={q} onChangeText={setQ} placeholder="Search any NSE ticker" placeholderTextColor={C.faint} style={st.search} autoCapitalize="characters" />
      {hits.length ? (
        <View style={st.hits}>
          {hits.map((h) => (
            <Pressable key={h.ticker} onPress={() => (setQ(''), router.push(`/company/${h.ticker}`))} style={st.hit}>
              <Text style={{ color: C.text, fontFamily: F.mono }}>{h.ticker}</Text>
              <Text style={{ color: C.sub, fontSize: 12 }}>{h.name}{h.held ? ' · held' : ''}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      <View style={st.row}>
        {WINDOWS.map((w) => (
          <Chip key={w.key} label={w.label} active={win === w.key} onPress={() => (setWidened('x'), setWin(w.key))} />
        ))}
        <View style={{ flex: 1 }} />
        <Chip label={bySector ? 'By tier' : 'By sector'} onPress={() => setBySector(!bySector)} />
      </View>

      <View style={st.macro}>
        <Label>Macro → your holdings</Label>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {[
            ['CL=F', 'Crude oil'],
            ['USDINR=X', 'USD/INR'],
            ['GC=F', 'Gold'],
          ].map(([sym, label]) => (
            <Chip key={sym} label={`${label} ›`} onPress={() => router.push(`/impact/${encodeURIComponent(sym)}`)} />
          ))}
        </View>
      </View>

      {loading && !data ? <Loading label="Loading your feed…" /> : null}
      {err ? <Empty title="Couldn't load the feed" body={err} /> : null}

      {sections.map((sec) =>
        sec.items.length ? (
          <View key={sec.key} style={{ gap: 10 }}>
            <View style={st.secHead}>
              {!bySector ? <View style={[st.bar, { backgroundColor: C.tier[sec.key] }]} /> : null}
              <Text style={[st.secTitle, !bySector ? { color: C.tier[sec.key] } : null]}>{sec.title}</Text>
              <View style={[st.countBadge, { backgroundColor: !bySector ? tint(C.tier[sec.key], 0.16) : C.surface2 }]}>
                <Text style={[st.countText, { color: !bySector ? C.tier[sec.key] : C.sub }]}>{sec.items.length}</Text>
              </View>
            </View>
            {sec.items.map((f) => (
              <Pressable key={f.id} onLongPress={() => dismiss(f)} delayLongPress={600}>
                <FilingCard f={f} compact />
              </Pressable>
            ))}
          </View>
        ) : null,
      )}

      {data && data.C.count ? (
        <Pressable onPress={() => setShowC(!showC)} style={st.cRow}>
          <Text style={{ color: C.sub, fontSize: 13 }}>
            {data.C.count} routine filings · {Object.entries(data.C.by_category).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(', ')}
          </Text>
          <Text style={{ color: C.faint }}>{showC ? '−' : '+'}</Text>
        </Pressable>
      ) : null}
      {showC && data
        ? data.C.items.map((c) => (
            <Pressable key={c.id} onPress={() => router.push(`/filing/${encodeURIComponent(c.id)}`)}>
              <Text style={{ color: C.faint, fontSize: 12, paddingHorizontal: 4 }} numberOfLines={1}>
                {c.ticker} · {c.headline}
              </Text>
            </Pressable>
          ))
        : null}
      {data && !data.counts.S && !data.counts.A && !data.counts.B && !data.C.count ? (
        <Empty title="No filings in this window" body="Try 7 d, or run the poll job." />
      ) : null}
      <Text style={{ color: C.faint, fontSize: 11, textAlign: 'center', marginTop: 8 }}>Long-press a card to dismiss it.</Text>
    </ScrollView>
  );
}

const st = themed(() => ({
  page: { padding: 16, gap: 14, paddingBottom: 120, width: '100%', maxWidth: 720, alignSelf: 'center' },
  hero: { gap: 10, paddingVertical: 6 },
  heroDate: { color: C.faint, fontSize: 11, letterSpacing: 1.2, fontFamily: F.mono },
  heroLine: { fontSize: 30, lineHeight: 36, fontWeight: '700' },
  counters: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  pill: { flexDirection: 'row', alignItems: 'baseline', gap: 6, borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  pillNum: { fontFamily: F.mono, fontSize: 16, fontWeight: '800' },
  pillLbl: { fontSize: 12, fontWeight: '700' },
  explain: { color: C.sub, fontSize: 13, lineHeight: 19 },
  bar: { width: 4, height: 18, borderRadius: 2 },
  secTitle: { fontSize: 15, fontWeight: '800', letterSpacing: 0.3, color: C.text },
  countBadge: { borderRadius: 999, paddingHorizontal: 8, paddingVertical: 1 },
  countText: { fontSize: 12, fontWeight: '800', fontFamily: F.mono },
  widened: { color: C.sub, fontSize: 12, fontStyle: 'italic' },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  search: { backgroundColor: C.surface, color: C.text, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, fontFamily: F.mono, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line },
  hits: { backgroundColor: C.surface, borderRadius: 10, overflow: 'hidden' },
  hit: { padding: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line, gap: 2 },
  secHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  macro: { gap: 8, padding: 12, backgroundColor: C.surface, borderRadius: 10 },
  cRow: { flexDirection: 'row', justifyContent: 'space-between', padding: 14, backgroundColor: C.surface, borderRadius: 10 },
}));
