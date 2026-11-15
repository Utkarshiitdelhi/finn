import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Switch, Text, TextInput, View } from 'react-native';

import { RuleCard } from '@/components/RuleCard';
import { Button, Card, Empty, Label, Serif } from '@/components/ui';
import { api, type Alert, type Rule } from '@/lib/api';
import { useFinn, useScreen } from '@/lib/finnContext';
import { ago, C, F } from '@/lib/theme';

export default function WatchScreen() {
  useScreen({ screen: 'watch' });
  const { bump } = useFinn();
  const [rules, setRules] = useState<Rule[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState('');
  const [draft, setDraft] = useState<{ spec?: any; label?: string; error?: string; closest?: any } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, a] = await Promise.all([api.rules(), api.alerts()]);
      setRules(r);
      setAlerts(a);
    } catch {}
    setLoading(false);
  }, []);
  useEffect(() => {
    load();
  }, [load, bump]);

  const parse = async () => {
    if (!text.trim()) return;
    setDraft(await api.parseRule(text).catch((e) => ({ error: e.message })));
  };

  const openHit = (a: Alert) => {
    const p = a.payload || {};
    if (p.filing_id) router.push(`/filing/${encodeURIComponent(p.filing_id)}`);
    else if (p.impact) router.push(`/impact/${encodeURIComponent(p.series)}`);
    else if (p.ticker) router.push(`/company/${p.ticker}`);
  };

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 120 }} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.sub} />}>
      <Card>
        <Label>Add a rule</Label>
        <TextInput
          value={text}
          onChangeText={setText}
          onSubmitEditing={parse}
          placeholder="e.g. Tell me if Titan moves more than 4% in a day"
          placeholderTextColor={C.faint}
          style={{ color: C.text, backgroundColor: C.surface2, borderRadius: 8, padding: 10 }}
        />
        <Button small label="Preview rule" onPress={parse} />
        <Text style={{ color: C.faint, fontSize: 11 }}>Or hold the F button and say it.</Text>
        {draft?.spec ? <RuleCard spec={draft.spec} label={draft.label || ''} onSaved={() => (setDraft(null), setText(''), load())} /> : null}
        {draft?.error ? (
          <View style={{ gap: 6 }}>
            <Text style={{ color: C.tier.A }}>{draft.error}</Text>
            {draft.closest ? <RuleCard spec={draft.closest} label="Closest rule FINN can watch" onSaved={load} /> : null}
          </View>
        ) : null}
      </Card>

      <Label>Recently triggered</Label>
      {alerts.length ? (
        alerts.slice(0, 8).map((a) => (
          <Pressable key={a.id} onPress={() => openHit(a)}>
            <Card>
              <Text style={{ color: C.faint, fontSize: 11, fontFamily: F.mono }}>{ago(a.at)} · {a.rule}</Text>
              <Serif style={{ fontSize: 15 }}>{a.message}</Serif>
            </Card>
          </Pressable>
        ))
      ) : (
        <Empty title="Nothing triggered yet" body="Price, volume and macro rules run after market close (4 pm IST); filing rules run every poll." />
      )}

      <Label>Watching · {rules.filter((r) => r.active).length}</Label>
      {rules.map((r) => (
        <Card key={r.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={{ color: r.active ? C.text : C.faint, fontSize: 14 }}>{r.label}</Text>
            <Text style={{ color: C.faint, fontSize: 11 }}>
              {r.source === 'default' ? 'default' : `added by ${r.source}`}
              {r.last_hit ? ` · last hit ${ago(r.last_hit.at)}` : ''}
            </Text>
          </View>
          <Switch value={r.active} onValueChange={(v) => api.toggleRule(r.id, v).then(load)} />
          {r.source !== 'default' ? (
            <Pressable onPress={() => api.deleteRule(r.id).then(load)} hitSlop={8}>
              <Text style={{ color: C.faint, fontSize: 16 }}>×</Text>
            </Pressable>
          ) : null}
        </Card>
      ))}
      <Text style={{ color: C.faint, fontSize: 11 }}>Every S-tier filing is pushed to you as well.</Text>
    </ScrollView>
  );
}
