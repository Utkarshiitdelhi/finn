import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { api } from '@/lib/api';
import { C, F } from '@/lib/theme';

import { Button, Card, Chip, Label } from './ui';

const OPS: Record<string, string> = { abs_gt: 'moves ±', gt: 'rises', lt: 'falls' };

/** Rule card with editable chips: ticker / metric / value. One tap confirms. */
export function RuleCard({ spec: initial, label, source = 'text', onSaved }: { spec: any; label: string; source?: string; onSaved?: () => void }) {
  const [spec, setSpec] = useState<any>(initial);
  const [saved, setSaved] = useState(false);
  const [savedLabel, setSavedLabel] = useState(label);
  const [err, setErr] = useState<string | null>(null);
  const numeric = typeof spec.value === 'number';
  const step = spec.type === 'volume' ? 0.5 : 1;
  const unit = spec.type === 'volume' ? '×' : '%';

  const save = async () => {
    try {
      const r = await api.createRule(spec, source);
      setSavedLabel(r.label);
      setSaved(true);
      onSaved?.();
    } catch (e: any) {
      setErr(e.message);
    }
  };

  return (
    <Card style={{ borderColor: saved ? C.up : C.line }}>
      <Label>{saved ? 'Watching' : 'New watch rule'}</Label>
      <Text style={{ color: C.text, fontFamily: F.serif, fontSize: 16 }}>{saved ? savedLabel : label || 'Watch this?'}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <Chip small label={spec.type} />
        {spec.scope ? <Chip small label={spec.scope === 'portfolio' ? 'all holdings' : spec.scope.replace('sector:', '')} /> : null}
        {spec.ticker ? <Chip small label={spec.ticker} /> : null}
        {spec.series ? <Chip small label={spec.series} /> : null}
        {spec.category ? <Chip small label={spec.category.replace('_', ' ')} /> : null}
        {spec.op && spec.type !== 'volume' ? (
          <Chip small label={OPS[spec.op]} onPress={saved ? undefined : () => setSpec({ ...spec, op: spec.op === 'abs_gt' ? 'lt' : spec.op === 'lt' ? 'gt' : 'abs_gt' })} />
        ) : null}
        {numeric ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            {!saved && (
              <Pressable onPress={() => setSpec({ ...spec, value: Math.max(step, +(spec.value - step).toFixed(1)) })} hitSlop={6}>
                <Text style={{ color: C.sub, fontSize: 18, paddingHorizontal: 6 }}>−</Text>
              </Pressable>
            )}
            <Text style={{ color: C.text, fontFamily: F.mono }}>
              {spec.value}
              {unit}
            </Text>
            {!saved && (
              <Pressable onPress={() => setSpec({ ...spec, value: +(spec.value + step).toFixed(1) })} hitSlop={6}>
                <Text style={{ color: C.sub, fontSize: 18, paddingHorizontal: 6 }}>+</Text>
              </Pressable>
            )}
          </View>
        ) : null}
        {spec.offset_days ? <Chip small label={`${-spec.offset_days} days before`} /> : null}
      </View>
      {!saved ? <Button small label="Confirm" onPress={save} /> : null}
      {err ? <Text style={{ color: C.down, fontSize: 12 }}>{err}</Text> : null}
    </Card>
  );
}
