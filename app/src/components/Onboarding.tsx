import AsyncStorage from '@react-native-async-storage/async-storage';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useEffect, useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';

import { C, F, themed, tint } from '@/lib/theme';

const KEY = 'finn.onboarded.v1';

type Step = { icon: React.ComponentProps<typeof Ionicons>['name']; title: string; body: string; extra?: 'tiers' };

// Only what an investor wouldn't guess: ranking, the research loop, and talking to FINN.
const STEPS: Step[] = [
  {
    icon: 'funnel-outline',
    title: 'What’s material to your portfolio',
    body: 'FINN reads every NSE filing for your holdings and ranks it by how much it matters. Urgent items reach your phone; routine filings are counted and tucked away, never lost.',
    extra: 'tiers',
  },
  {
    icon: 'search-outline',
    title: 'Dig in for the full story',
    body: 'Every card opens cited research, including the promise tracker: what management guided vs. what they actually delivered.',
  },
  {
    icon: 'sparkles',
    title: 'Ask FINN, or just say it',
    body: 'Hold Ask FINN and say “alert me if Titan falls 5%”, and it becomes a watch rule. The macro card shows how crude, rupee or gold moves hit your holdings.',
  },
];

/** Three-card intro on first launch. Skippable; never shown again. */
export function Onboarding() {
  const [show, setShow] = useState(false);
  const [i, setI] = useState(0);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((v) => setShow(!v))
      .catch(() => setShow(false));
  }, []);

  const done = () => {
    setShow(false);
    AsyncStorage.setItem(KEY, '1').catch(() => {});
  };

  if (!show) return null;
  const s = STEPS[i];
  const last = i === STEPS.length - 1;
  return (
    <Modal transparent animationType="fade" visible onRequestClose={done}>
      <View style={st.backdrop}>
        <View style={st.card}>
          <View style={st.iconWrap}>
            <Ionicons name={s.icon} size={26} color={C.accent} />
          </View>
          <Text style={st.step}>
            {i + 1} of {STEPS.length}
          </Text>
          <Text style={st.title}>{s.title}</Text>
          <Text style={st.body}>{s.body}</Text>
          {s.extra === 'tiers' ? (
            <View style={st.tiers}>
              {(
                [
                  ['S', 'Urgent'],
                  ['A', 'Worth a look'],
                  ['B', 'For the record'],
                ] as const
              ).map(([t, l]) => (
                <View key={t} style={[st.tier, { backgroundColor: tint(C.tier[t], 0.16), borderColor: tint(C.tier[t], 0.5) }]}>
                  <Text style={[st.tierText, { color: C.tier[t] }]}>{l}</Text>
                </View>
              ))}
            </View>
          ) : null}
          <View style={st.dots}>
            {STEPS.map((_, k) => (
              <View key={k} style={[st.dot, k === i ? { backgroundColor: C.accent, width: 18 } : null]} />
            ))}
          </View>
          <View style={st.row}>
            {!last ? (
              <Pressable onPress={done} hitSlop={10}>
                <Text style={st.skip}>Skip</Text>
              </Pressable>
            ) : (
              <View />
            )}
            <Pressable onPress={() => (last ? done() : setI(i + 1))} style={st.next}>
              <Text style={st.nextText}>{last ? 'Get started' : 'Next'}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const st = themed(() => ({
  backdrop: { flex: 1, backgroundColor: '#000000B3', justifyContent: 'center', padding: 24 },
  card: { backgroundColor: C.surface, borderRadius: 20, padding: 24, gap: 12, width: '100%', maxWidth: 420, alignSelf: 'center', borderWidth: 1, borderColor: C.line },
  iconWrap: { width: 52, height: 52, borderRadius: 16, backgroundColor: tint(C.accent, 0.15), alignItems: 'center', justifyContent: 'center' },
  step: { color: C.faint, fontSize: 11, letterSpacing: 1, fontFamily: F.mono },
  title: { color: C.text, fontFamily: F.serif, fontSize: 24, fontWeight: '700', lineHeight: 30 },
  body: { color: C.sub, fontSize: 15, lineHeight: 22 },
  tiers: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  tier: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 },
  tierText: { fontSize: 12, fontWeight: '800' },
  dots: { flexDirection: 'row', gap: 6, marginTop: 4 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: C.line },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 },
  skip: { color: C.sub, fontSize: 15, fontWeight: '600' },
  next: { backgroundColor: C.accent, borderRadius: 999, paddingHorizontal: 22, paddingVertical: 11 },
  nextText: { color: C.accentText, fontSize: 15, fontWeight: '800' },
}));
