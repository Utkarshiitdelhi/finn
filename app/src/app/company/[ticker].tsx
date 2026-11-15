import { Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { FilingCard } from '@/components/FilingCard';
import { RuleCard } from '@/components/RuleCard';
import { Bars, Sparkline } from '@/components/Sparkline';
import { Card, Chip, Empty, Label, Loading, Mono, Serif } from '@/components/ui';
import { api } from '@/lib/api';
import { useScreen } from '@/lib/finnContext';
import { C, F, num, pct, signColor, themed } from '@/lib/theme';

const VERDICT: Record<string, string> = new Proxy({} as Record<string, string>, {
  get: (_t, k: string) => ({ Delivered: C.up, Partly: C.tier.A, Missed: C.down, Pending: C.sub, "Can't verify": C.faint } as Record<string, string>)[k],
});

function PromiseCard({ c }: { c: any }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Card>
      <Label>Promise tracker</Label>
      <Serif style={{ fontSize: 20 }}>{c.scorecard?.text}</Serif>
      <Text style={st.src}>{c.source}</Text>
      {c.empty_reason ? <Text style={{ color: C.sub }}>{c.empty_reason}</Text> : null}
      {(c.rows || []).map((r: any) => (
        <Pressable key={r.key} onPress={() => setOpen(open === r.key ? null : r.key)} style={st.prow}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={{ flex: 1, color: C.text, fontSize: 14 }} numberOfLines={1}>
              {r.metric_label}
              {r.period ? <Text style={{ color: C.faint }}> · {r.period}</Text> : null}
            </Text>
            <View style={[st.verdict, { borderColor: VERDICT[r.verdict] }]}>
              <Text style={{ color: VERDICT[r.verdict], fontSize: 11, fontWeight: '600' }}>{r.verdict}</Text>
            </View>
          </View>
          <Text style={{ color: C.sub, fontSize: 12 }}>
            Said <Text style={{ fontFamily: F.mono, color: C.text }}>{r.said}</Text>
            {r.revised ? <Text style={{ color: C.tier.A }}> · revised</Text> : null}
            {r.delivered ? ` · ${r.delivered}` : ''}
          </Text>
          {open === r.key ? (
            <View style={st.quote}>
              <Text style={{ color: C.text, fontFamily: F.serif, fontSize: 14, lineHeight: 20 }}>“{r.quote}”</Text>
              <Text style={st.src}>
                {r.speaker ? `${r.speaker} · ` : ''}
                {r.call} call, p.{r.page}
              </Text>
              {r.history?.length > 1 ? (
                <Text style={st.src}>History: {r.history.map((h: any) => `${h.call}: ${h.said}`).join(' → ')}</Text>
              ) : null}
              {r.source_url ? (
                <Pressable onPress={() => Linking.openURL(r.source_url)}>
                  <Text style={{ color: C.accent, fontSize: 12 }}>Open transcript ↗</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}
        </Pressable>
      ))}
    </Card>
  );
}

function SnapshotCard({ c }: { c: any }) {
  return (
    <Card>
      <Label>Snapshot</Label>
      <Text style={{ color: C.text, fontFamily: F.serif, fontSize: 15, lineHeight: 22 }} numberOfLines={6}>
        {c.what_it_does || 'Not in the sources.'}
      </Text>
      {(c.segments || []).length ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {c.segments.map((s: any) => (
            <Chip small key={s.name} label={`${s.name}${s.share_of_revenue_pct ? ` ${s.share_of_revenue_pct}%` : ''}`} />
          ))}
        </View>
      ) : null}
      {(c.key_facts || []).map((k: any, i: number) => (
        <Text key={i} style={{ color: C.sub, fontSize: 13 }}>
          · {k.fact} <Text style={{ color: C.faint }}>p.{k.page}</Text>
        </Text>
      ))}
      <Text style={st.src}>{c.source}</Text>
    </Card>
  );
}

function NumbersCard({ c }: { c: any }) {
  return (
    <Card>
      <Label>Numbers + trajectory · {c.unit}</Label>
      <View style={st.tr}>
        <Text style={[st.th, { flex: 1.2, textAlign: 'left' }]}>Year</Text>
        <Text style={st.th}>Revenue</Text>
        <Text style={st.th}>OPM</Text>
        <Text style={st.th}>PAT</Text>
      </View>
      {c.years.map((y: any) => (
        <View key={y.period} style={st.tr}>
          <Mono style={[st.td, { flex: 1.2, textAlign: 'left', color: C.sub }]}>{y.period}</Mono>
          <Mono style={st.td}>{num(y.revenue)}</Mono>
          <Mono style={st.td}>{y.opm_pct ?? '—'}%</Mono>
          <Mono style={st.td}>{num(y.pat)}</Mono>
        </View>
      ))}
      <Text style={{ color: C.sub, fontSize: 12 }}>
        Revenue CAGR <Mono>{pct(c.cagr.revenue_3y)}</Mono> 3y, <Mono>{pct(c.cagr.revenue_5y)}</Mono> 5y · PAT <Mono>{pct(c.cagr.pat_3y)}</Mono> 3y
      </Text>
      <Label style={{ marginTop: 6 }}>Last 8 quarters · PAT</Label>
      <Bars values={c.quarters.map((q: any) => q.pat)} />
      <Text style={st.src}>{c.source}</Text>
    </Card>
  );
}

function CashCard({ c }: { c: any }) {
  return (
    <Card>
      <Label>Cash quality</Label>
      <Serif>
        {c.line || 'Not enough data'} <Mono style={{ color: c.cfo_to_pat_5y >= 0.9 ? C.up : C.tier.A }}>{c.cfo_to_pat_5y ?? '—'}×</Mono>
      </Serif>
      <Text style={{ color: C.sub, fontSize: 12 }}>
        {c.years.map((y: any) => `${y.period.slice(-4)} ${y.ratio ?? '—'}×`).join('  ')}
      </Text>
      <Text style={st.src}>{c.note}</Text>
    </Card>
  );
}

function BullBearCard({ c }: { c: any }) {
  return (
    <Card>
      <Label>Bull vs bear</Label>
      {c.bull.map((p: any, i: number) => (
        <Text key={'b' + i} style={{ color: C.text, fontSize: 14 }}>
          <Text style={{ color: C.up }}>▲ </Text>
          {p.point} <Text style={{ color: C.faint, fontSize: 11 }}>[{p.cites.join(', ')}]</Text>
        </Text>
      ))}
      {c.bear.map((p: any, i: number) => (
        <Text key={'r' + i} style={{ color: C.text, fontSize: 14 }}>
          <Text style={{ color: C.down }}>▼ </Text>
          {p.point} <Text style={{ color: C.faint, fontSize: 11 }}>[{p.cites.join(', ')}]</Text>
        </Text>
      ))}
      <Text style={st.src}>{c.source}</Text>
    </Card>
  );
}

function BalanceCard({ c }: { c: any }) {
  return (
    <Card>
      <Label>Balance sheet</Label>
      <Text style={{ color: C.sub, fontSize: 13 }}>
        Debt / equity: {c.years.map((y: any) => `${y.period.slice(-4)} ${y.de ?? '—'}`).join('  ')}
      </Text>
      <Text style={st.src}>{c.source}</Text>
    </Card>
  );
}

const CARDS: Record<string, (p: { c: any }) => React.JSX.Element> = {
  promise: PromiseCard, snapshot: SnapshotCard, numbers: NumbersCard, cash: CashCard, bullbear: BullBearCard, balance: BalanceCard,
};

export default function CompanyScreen() {
  const { ticker } = useLocalSearchParams<{ ticker: string }>();
  const T = String(ticker).toUpperCase();
  useScreen({ screen: 'company', ticker: T });
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [watch, setWatch] = useState<any>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let alive = true;
    let failures = 0;
    const poll = async () => {
      try {
        const d = await api.company(T);
        if (!alive) return;
        failures = 0;
        setData(d);
        if (d.status === 'building') timer.current = setTimeout(poll, 2500);
      } catch (e: any) {
        // The build keeps running on the server; a blip (app backgrounded, server waking) is not a failure.
        if (!alive) return;
        failures += 1;
        if (failures < 30) timer.current = setTimeout(poll, Math.min(2500 * failures, 10000));
        else setErr(e.message);
      }
    };
    poll();
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [T]);

  if (err) return <Empty title={`Couldn't research ${T}`} body={err} />;
  if (!data) return <Loading />;
  if (data.status === 'building' || data.status === 'error') {
    const steps = data.steps || [];
    return (
      <View style={{ padding: 20, gap: 10, width: '100%', maxWidth: 720, alignSelf: 'center' }}>
        <Stack.Screen options={{ title: T }} />
        <Serif style={{ fontSize: 20 }}>{data.status === 'error' ? `Couldn't build ${T}` : `Researching ${T}…`}</Serif>
        <Text style={{ color: C.sub, fontSize: 13 }}>First run reads the filings and transcripts; after that it opens instantly.</Text>
        {steps.map((s: any, i: number) => (
          <Text key={i} style={{ color: i === steps.length - 1 ? C.text : C.faint, fontFamily: F.mono, fontSize: 12 }}>
            {i === steps.length - 1 && data.status !== 'error' ? '› ' : '✓ '}
            {s.msg}
          </Text>
        ))}
        {data.error ? <Text style={{ color: C.down }}>{data.error}</Text> : <Loading />}
      </View>
    );
  }

  const v = data.view;
  const prices: number[] = (data.prices || []).map((p: any) => p.close);
  const last = prices[prices.length - 1];
  const chg = prices.length > 1 ? ((last - prices[prices.length - 2]) / prices[prices.length - 2]) * 100 : null;
  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 140, width: '100%', maxWidth: 720, alignSelf: 'center' }}>
      <Stack.Screen options={{ title: T }} />
      <View style={{ gap: 6 }}>
        <Serif style={{ fontSize: 24 }}>{v.name}</Serif>
        <View style={{ flexDirection: 'row', gap: 12, alignItems: 'baseline' }}>
          {last ? <Mono style={{ fontSize: 20 }}>₹{num(last, 1)}</Mono> : null}
          {chg !== null ? <Mono style={{ color: signColor(chg) }}>{pct(chg)}</Mono> : null}
          {v.ratios?.['Market Cap'] ? <Text style={{ color: C.sub, fontSize: 12 }}>MCap ₹{num(v.ratios['Market Cap'])} cr</Text> : null}
          {data.holding ? <Chip small label={`${(data.holding.weight * 100).toFixed(0)}% of you`} /> : null}
        </View>
        <Sparkline values={prices} />
      </View>
      {v.order.filter((k: string) => v.cards[k]).map((k: string) => {
        const Comp = CARDS[k];
        return Comp ? <Comp key={k} c={v.cards[k]} /> : null;
      })}

      <Card>
        <Label>Watch this</Label>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          <Chip label="Next results" onPress={() => setWatch({ type: 'filing', scope: T, category: 'results' })} />
          <Chip label="Concall transcript" onPress={() => setWatch({ type: 'filing', scope: T, category: 'earnings_call' })} />
          <Chip label="±5% day" onPress={() => setWatch({ type: 'price', scope: T, op: 'abs_gt', value: 5 })} />
          <Chip label="2 days before results" onPress={() => setWatch({ type: 'event', ticker: T, offset_days: -2 })} />
        </View>
        {watch ? <RuleCard key={JSON.stringify(watch)} spec={watch} label="" source="form" /> : null}
      </Card>

      {data.filings?.length ? <Label>Recent filings</Label> : null}
      {(data.filings || []).slice(0, 5).map((f: any) => (
        <FilingCard key={f.id} f={f} compact />
      ))}
    </ScrollView>
  );
}

const st = themed(() => ({
  src: { color: C.faint, fontSize: 11 },
  prow: { paddingVertical: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line, gap: 3 },
  verdict: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
  quote: { backgroundColor: C.surface2, borderRadius: 8, padding: 10, gap: 4, marginTop: 4 },
  tr: { flexDirection: 'row' },
  th: { flex: 1, color: C.faint, fontSize: 11, textAlign: 'right' },
  td: { flex: 1, fontSize: 13, textAlign: 'right' },
}));
