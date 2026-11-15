import { Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ScrollView, Text } from 'react-native';

import { FilingCard } from '@/components/FilingCard';
import { Card, Empty, Label, Loading } from '@/components/ui';
import { api, type FeedCard } from '@/lib/api';
import { useScreen } from '@/lib/finnContext';
import { C } from '@/lib/theme';

export default function FilingScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const fid = decodeURIComponent(String(id));
  const [f, setF] = useState<FeedCard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useScreen({ screen: 'filing', filing_id: fid, ticker: f?.ticker });

  useEffect(() => {
    api.filing(fid).then(setF).catch((e) => setErr(e.message));
  }, [fid]);

  if (err) return <Empty title="Filing not found" body={err} />;
  if (!f) return <Loading />;
  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 120 }}>
      <Stack.Screen options={{ title: f.ticker }} />
      <FilingCard f={f} />
      <Card>
        <Label>As filed</Label>
        <Text style={{ color: C.text, fontSize: 13 }}>{f.subject}</Text>
        {f.text ? <Text style={{ color: C.sub, fontSize: 13, lineHeight: 19 }}>{f.text}</Text> : null}
      </Card>
    </ScrollView>
  );
}
