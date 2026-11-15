import { Tabs } from 'expo-router';
import { Text, type ColorValue } from 'react-native';

import { C, F } from '@/lib/theme';

const icon = (glyph: string) => ({ color }: { color: ColorValue }) => <Text style={{ color, fontSize: 18, fontFamily: F.mono }}>{glyph}</Text>;

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: C.bg },
        headerTintColor: C.text,
        headerTitleStyle: { fontFamily: F.serif, fontSize: 22 },
        headerShadowVisible: false,
        tabBarStyle: { backgroundColor: C.bg, borderTopColor: C.line },
        tabBarActiveTintColor: C.text,
        tabBarInactiveTintColor: C.faint,
        sceneStyle: { backgroundColor: C.bg },
      }}>
      <Tabs.Screen name="index" options={{ title: 'Feed', tabBarIcon: icon('≡') }} />
      <Tabs.Screen name="watch" options={{ title: 'Watch', tabBarIcon: icon('◉') }} />
      <Tabs.Screen name="portfolio" options={{ title: 'Portfolio', tabBarIcon: icon('◫') }} />
    </Tabs>
  );
}
