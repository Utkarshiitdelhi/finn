import { router } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { FilingCard } from '@/components/FilingCard';
import { Chip, Empty, Label, Loading, Serif } from '@/components/ui';
import { api, type Feed, type FeedCard } from '@/lib/api';
import { useFinn, useScreen } from '@/lib/finnContext';
import { C, F } from '@/lib/theme';

const WINDOWS = [
  { key: '24h', label: '24 h' },
  { key: '3d', label: '3 d' },
  { key: '7d', label: '7 d' },
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

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setData(await api.feed(win));
    } catch (e: any) {
      setErr(e.name === 'AbortError' ? 'Server is waking up (free tier). Pull to retry.' : e.message);
    } finally {
      setLoading(false);
    }
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
    if (!bySector) return (['S', 'A', 'B'] as const).map((t) => ({ key: t, title: { S: 'Needs you', A: 'Worth a look', B: 'For the record' }[t], items: data[t] }));
    const groups: Record<string, FeedCard[]> = {};
    [...data.S, ...data.A, ...data.B].forEach((f) => (groups[f.sector || 'Other'] ||= []).push(f));
    return Object.entries(groups).map(([k, items]) => ({ key: k, title: k, items }));
  }, [data, bySector]);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={st.page} refreshControl={<RefreshControl refreshing={loading && !!data} onRefresh={load} tintColor={C.sub} />}>
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
          <Chip key={w.key} label={w.label} active={win === w.key} onPress={() => setWin(w.key)} />
        ))}
        <View style={{ flex: 1 }} />
        <Chip label={bySector ? 'By tier' : 'By sector'} onPress={() => setBySector(!bySector)} />
      </View>

      {data ? (
        <Serif style={{ color: C.sub, fontSize: 15 }}>
          {data.counts.S + data.counts.A > 0
            ? `${data.counts.S + data.counts.A} thing${data.counts.S + data.counts.A === 1 ? '' : 's'} need you. `
            : 'Nothing urgent. '}
          {data.C.count} routine filing{data.C.count === 1 ? '' : 's'} hidden.
        </Serif>
      ) : null}

      {loading && !data ? <Loading label="Loading your feed…" /> : null}
      {err ? <Empty title="Couldn't load the feed" body={err} /> : null}

      {sections.map((sec) =>
        sec.items.length ? (
          <View key={sec.key} style={{ gap: 10 }}>
            <View style={st.secHead}>
              {!bySector ? <View style={[st.dot, { backgroundColor: C.tier[sec.key] }]} /> : null}
              <Label>{sec.title} · {sec.items.length}</Label>
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

const st = StyleSheet.create({
  page: { padding: 16, gap: 14, paddingBottom: 120 },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  search: { backgroundColor: C.surface, color: C.text, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, fontFamily: F.mono, borderWidth: StyleSheet.hairlineWidth, borderColor: C.line },
  hits: { backgroundColor: C.surface, borderRadius: 10, overflow: 'hidden' },
  hit: { padding: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line, gap: 2 },
  secHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  cRow: { flexDirection: 'row', justifyContent: 'space-between', padding: 14, backgroundColor: C.surface, borderRadius: 10 },
});
