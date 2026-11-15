import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';

import { Card, Chip, Label, Loading, Mono } from '@/components/ui';
import { api } from '@/lib/api';
import { useScreen } from '@/lib/finnContext';
import { C, F } from '@/lib/theme';

const CATS = [
  ['results', 'Results'], ['management_change', 'Management'], ['credit_rating', 'Ratings'], ['M&A', 'M&A'],
  ['pledging', 'Pledges'], ['litigation', 'Litigation'], ['fund_raise', 'Fund raise'], ['insider_trading', 'Insider'],
  ['capex', 'Capex'], ['press_release', 'Orders / PR'], ['dividend', 'Dividend'],
] as const;

export default function PortfolioScreen() {
  useScreen({ screen: 'portfolio' });
  const [data, setData] = useState<any>(null);
  const load = useCallback(() => api.portfolio().then(setData).catch(() => {}), []);
  useEffect(() => {
    load();
  }, [load]);
  if (!data) return <Loading />;
  const prefs = data.prefs || {};
  const starred: string[] = prefs.starred_categories || [];
  const toggleCat = async (c: string) => {
    const next = starred.includes(c) ? starred.filter((x) => x !== c) : [...starred, c];
    await api.prefs({ starred_categories: next });
    load();
  };
  const bump = async (key: 'price_pct' | 'vol_ratio', d: number) => {
    const cur = prefs[key] ?? (key === 'price_pct' ? 5 : 2);
    await api.prefs({ [key]: Math.max(key === 'price_pct' ? 1 : 1.5, +(cur + d).toFixed(1)) });
    load();
  };
  const sectors = Object.entries(
    data.holdings.reduce((acc: Record<string, number>, h: any) => ({ ...acc, [h.sector]: (acc[h.sector] || 0) + h.weight }), {}),
  ).sort((a: any, b: any) => b[1] - a[1]);

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 120 }}>
      <Card>
        <Label>Default alerts</Label>
        {(
          [
            ['price_pct', 'Price move', '%', 1],
            ['vol_ratio', 'Volume vs 20-day avg', '×', 0.5],
          ] as const
        ).map(([k, l, u, step]) => (
          <View key={k} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ color: C.text }}>{l}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Pressable onPress={() => bump(k, -step)} hitSlop={8}>
                <Text style={{ color: C.sub, fontSize: 20 }}>−</Text>
              </Pressable>
              <Mono>
                {k === 'price_pct' ? '±' : ''}
                {prefs[k] ?? (k === 'price_pct' ? 5 : 2)}
                {u}
              </Mono>
              <Pressable onPress={() => bump(k, step)} hitSlop={8}>
                <Text style={{ color: C.sub, fontSize: 20 }}>+</Text>
              </Pressable>
            </View>
          </View>
        ))}
        <Text style={{ color: C.faint, fontSize: 11 }}>Applies to every holding. Every S-tier filing is pushed too.</Text>
      </Card>

      <Card>
        <Label>Categories you care about</Label>
        <Text style={{ color: C.faint, fontSize: 11 }}>Starred categories get a 1.25× boost in the ranking.</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {CATS.map(([k, l]) => (
            <Chip key={k} label={(starred.includes(k) ? '★ ' : '') + l} active={starred.includes(k)} onPress={() => toggleCat(k)} />
          ))}
        </View>
      </Card>

      <Card>
        <Label>Sectors</Label>
        {sectors.map(([s, w]: any) => (
          <View key={s} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={{ color: C.sub, width: 110, fontSize: 13 }}>{s}</Text>
            <View style={{ flex: 1, height: 6, backgroundColor: C.surface2, borderRadius: 3 }}>
              <View style={{ width: `${w * 100 * 3}%`, maxWidth: '100%', height: 6, backgroundColor: C.sub, borderRadius: 3 }} />
            </View>
            <Mono style={{ fontSize: 12, width: 36, textAlign: 'right' }}>{(w * 100).toFixed(0)}%</Mono>
          </View>
        ))}
      </Card>

      <Label>Holdings · {data.holdings.length}</Label>
      {data.holdings.map((h: any) => (
        <Pressable key={h.ticker} onPress={() => router.push(`/company/${h.ticker}`)}>
          <Card style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontFamily: F.mono }}>{h.ticker}</Text>
              <Text style={{ color: C.faint, fontSize: 12 }}>
                {h.name} · {h.sector}
              </Text>
            </View>
            <Mono style={{ color: C.sub }}>{(h.weight * 100).toFixed(0)}%</Mono>
            <Pressable onPress={() => api.star(h.ticker).then(load)} hitSlop={10}>
              <Text style={{ color: h.starred ? C.tier.A : C.faint, fontSize: 18 }}>{h.starred ? '★' : '☆'}</Text>
            </Pressable>
          </Card>
        </Pressable>
      ))}
    </ScrollView>
  );
}
