import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Linking, Pressable, ScrollView, Text, View } from 'react-native';

import { Card, Empty, Label, Loading, Mono, Serif } from '@/components/ui';
import { api } from '@/lib/api';
import { useScreen } from '@/lib/finnContext';
import { C, F, pct } from '@/lib/theme';

/** Impact tree: event -> disclosed exposure -> your holdings, each edge with its annual-report quote. */
export default function ImpactSheet() {
  const { series } = useLocalSearchParams<{ series: string }>();
  const sid = decodeURIComponent(String(series));
  useScreen({ screen: 'impact' });
  const [d, setD] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.impact(sid).then(setD).catch((e) => setErr(e.message));
  }, [sid]);
  if (err) return <Empty title="No exposure map" body={err} />;
  if (!d) return <Loading />;
  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 80, width: '100%', maxWidth: 720, alignSelf: 'center' }}>
      <Serif style={{ fontSize: 22 }}>
        {d.factor} {d.move_pct != null ? <Mono style={{ color: d.move_pct >= 0 ? C.up : C.down }}>{pct(d.move_pct)}</Mono> : null}
      </Serif>
      <Text style={{ color: C.sub, fontSize: 13 }}>
        {d.edges.length ? `${d.edges.length} of your holdings disclose exposure to ${d.factor}.` : `None of your holdings disclose exposure to ${d.factor}.`}
      </Text>
      {d.edges.map((e: any) => (
        <Pressable key={e.ticker} onPress={() => setOpen(open === e.ticker ? null : e.ticker)}>
          <Card>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Text style={{ color: C.faint, fontFamily: F.mono }}>{d.factor} →</Text>
              <Text style={{ color: e.sign === '+' ? C.up : C.down, fontFamily: F.mono, fontSize: 18 }}>{e.sign}</Text>
              <Text style={{ color: C.text, fontFamily: F.mono, flex: 1 }}>{e.ticker}</Text>
              <Label>{e.strength}</Label>
            </View>
            {open === e.ticker ? (
              <View style={{ gap: 4 }}>
                <Text style={{ color: C.text, fontFamily: F.serif, lineHeight: 20 }}>“{e.quote}”</Text>
                <Text style={{ color: C.faint, fontSize: 11 }}>
                  {e.source}, p.{e.page}
                </Text>
                <View style={{ flexDirection: 'row', gap: 16 }}>
                  <Pressable onPress={() => router.push(`/company/${e.ticker}`)}>
                    <Text style={{ color: C.accent, fontSize: 12 }}>Dig in →</Text>
                  </Pressable>
                  {e.source_url ? (
                    <Pressable onPress={() => Linking.openURL(e.source_url)}>
                      <Text style={{ color: C.accent, fontSize: 12 }}>Annual report ↗</Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            ) : null}
          </Card>
        </Pressable>
      ))}
      <Text style={{ color: C.faint, fontSize: 11 }}>{d.note}</Text>
    </ScrollView>
  );
}
