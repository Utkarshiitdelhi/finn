import Ionicons from '@expo/vector-icons/Ionicons';
import { RecordingPresets, requestRecordingPermissionsAsync, setAudioModeAsync, useAudioRecorder } from 'expo-audio';
import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import * as Speech from 'expo-speech';
import { useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api, type AssistantReply } from '@/lib/api';
import { useFinn } from '@/lib/finnContext';
import { C, F, themed } from '@/lib/theme';

import { RuleCard } from './RuleCard';
import { Card, Label } from './ui';

const SUGGEST: Record<string, string[]> = {
  feed: ['What needs me today?', 'Alert me if any holding falls 5%'],
  company: ['What did they say about margins?', 'Remind me when the transcript is out'],
  filing: ['Why does this matter to me?', 'Watch this company'],
  watch: ['If crude rises 3% in a day', 'Any management change at my banks'],
  portfolio: ['Open Infosys'],
  impact: ['Which holding is most exposed?'],
};

/** Floating FINN button on every screen: tap to type, hold to talk. */
export function FinnButton() {
  const insets = useSafeAreaInsets();
  const { ctx, refresh } = useFinn();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [reply, setReply] = useState<AssistantReply | null>(null);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const startedAt = useRef(0);

  const handle = (r: AssistantReply) => {
    setReply(r);
    if (r.say) Speech.speak(r.say, { rate: 1.05 }); // at most two sentences; the screen carries the detail
    if (r.intent === 'go' && r.route) {
      setOpen(false);
      router.push(r.route as any);
    }
  };

  const send = async (q?: string) => {
    const t = (q ?? text).trim();
    if (!t) return;
    setBusy(true);
    setReply(null);
    try {
      handle(await api.assistant(t, ctx));
      setText('');
    } catch (e: any) {
      setReply({ intent: 'error', say: e.message || 'Something went wrong' });
    } finally {
      setBusy(false);
    }
  };

  const startTalk = async () => {
    const perm = await requestRecordingPermissionsAsync();
    if (!perm.granted) {
      setOpen(true);
      setReply({ intent: 'error', say: 'Microphone permission is off. You can still type.' });
      return;
    }
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
    Speech.stop();
    await recorder.prepareToRecordAsync();
    recorder.record();
    startedAt.current = Date.now();
    setRecording(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
  };

  const stopTalk = async () => {
    if (!recording) return;
    setRecording(false);
    await recorder.stop();
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false });
    if (Date.now() - startedAt.current < 600 || !recorder.uri) return;
    setOpen(true);
    setBusy(true);
    setReply(null);
    try {
      handle(await api.voice(recorder.uri, ctx));
    } catch (e: any) {
      setReply({ intent: 'error', say: e.message || 'Voice failed; try typing.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        onLongPress={startTalk}
        onPressOut={stopTalk}
        delayLongPress={250}
        style={[st.fab, { bottom: insets.bottom + 64 }, recording && st.fabRec]}
        accessibilityLabel="FINN assistant. Tap to type, hold to talk.">
        <Ionicons name={recording ? 'mic' : 'sparkles'} size={20} color={C.accentText} />
        <Text style={st.fabText}>{recording ? 'Listening…' : 'Ask FINN'}</Text>
      </Pressable>
      {recording ? (
        <View style={[st.listening, { bottom: insets.bottom + 132 }]}>
          <Text style={{ color: C.text, fontSize: 13 }}>Listening… release to send</Text>
        </View>
      ) : null}

      <Modal visible={open} animationType="slide" transparent onRequestClose={() => setOpen(false)}>
        <Pressable style={st.backdrop} onPress={() => setOpen(false)} />
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={[st.sheet, { paddingBottom: insets.bottom + 12 }]}>
          <View style={st.grab} />
          <Label>
            FINN{ctx.ticker ? ` · ${ctx.ticker}` : ''} · {ctx.screen}
          </Label>
          <ScrollView style={{ maxHeight: 380 }} contentContainerStyle={{ gap: 10, paddingVertical: 8 }} keyboardShouldPersistTaps="handled">
            {reply?.heard ? <Text style={{ color: C.faint, fontStyle: 'italic' }}>“{reply.heard}”</Text> : null}
            {busy ? <ActivityIndicator color={C.sub} /> : null}
            {reply?.intent === 'command' && reply.rule ? (
              <RuleCard spec={reply.rule.spec} label={reply.rule.label} source={reply.heard ? 'voice' : 'text'} onSaved={refresh} />
            ) : null}
            {reply?.intent === 'command' && !reply.rule ? (
              <Card>
                <Text style={{ color: C.text }}>{reply.error}</Text>
                {reply.closest ? <RuleCard spec={reply.closest} label={reply.closest_label || ''} onSaved={refresh} /> : null}
              </Card>
            ) : null}
            {reply?.intent === 'ask' ? (
              <Card>
                <Text style={{ color: C.text, fontFamily: F.serif, fontSize: 16, lineHeight: 22 }}>{reply.answer}</Text>
                {(reply.cites || []).map((c: any, i: number) => (
                  <Pressable
                    key={i}
                    onPress={() => {
                      setOpen(false);
                      router.push((c.type === 'filing' ? `/filing/${encodeURIComponent(c.id)}` : `/company/${c.ticker}`) as any);
                    }}>
                    <Text style={{ color: C.accent, fontSize: 12 }}>↗ {c.label || `${c.ticker} · ${c.card}`}</Text>
                  </Pressable>
                ))}
              </Card>
            ) : null}
            {reply?.intent === 'error' || reply?.intent === 'none' ? <Text style={{ color: C.down }}>{reply.say}</Text> : null}
            {!reply && !busy ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                {(SUGGEST[ctx.screen] || SUGGEST.feed).map((q) => (
                  <Pressable key={q} onPress={() => send(q)} style={st.suggest}>
                    <Text style={{ color: C.sub, fontSize: 13 }}>{q}</Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
          </ScrollView>
          <View style={st.inputRow}>
            <TextInput
              value={text}
              onChangeText={setText}
              placeholder="Ask, or say “alert me if…”"
              placeholderTextColor={C.faint}
              style={st.input}
              onSubmitEditing={() => send()}
              returnKeyType="send"
              autoFocus={!reply}
            />
            <Pressable onPress={() => send()} style={st.send}>
              <Text style={{ color: C.accentText, fontWeight: '700' }}>↑</Text>
            </Pressable>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}

const st = themed(() => ({
  fab: {
    position: 'absolute', right: 16, height: 52, borderRadius: 26, backgroundColor: C.accent, paddingHorizontal: 18,
    flexDirection: 'row', alignItems: 'center', gap: 8,
    elevation: 8, shadowColor: C.accent, shadowOpacity: 0.45, shadowRadius: 12, shadowOffset: { width: 0, height: 4 },
  },
  fabRec: { backgroundColor: C.down, transform: [{ scale: 1.06 }] },
  fabText: { color: C.accentText, fontSize: 15, fontWeight: '800' },
  listening: { position: 'absolute', right: 18, backgroundColor: C.surface2, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8 },
  backdrop: { flex: 1, backgroundColor: '#0008' },
  sheet: { backgroundColor: C.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: 16, gap: 8 },
  grab: { alignSelf: 'center', width: 36, height: 4, borderRadius: 2, backgroundColor: C.line, marginBottom: 4 },
  inputRow: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  input: { flex: 1, backgroundColor: C.surface2, color: C.text, borderRadius: 999, paddingHorizontal: 16, paddingVertical: 10, fontSize: 15 },
  send: { width: 40, height: 40, borderRadius: 20, backgroundColor: C.accent, alignItems: 'center', justifyContent: 'center' },
  suggest: { borderWidth: 1, borderColor: C.line, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
}));
