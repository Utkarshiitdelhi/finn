import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';
import type { ComponentProps } from 'react';
import { Pressable, type ColorValue } from 'react-native';

import { C, F } from '@/lib/theme';
import { useThemeMode } from '@/lib/themeContext';

type IconName = ComponentProps<typeof Ionicons>['name'];
const icon =
  (name: IconName, active: IconName) =>
  ({ color, focused }: { color: ColorValue; focused: boolean }) => <Ionicons name={focused ? active : name} size={22} color={color as string} />;

function ThemeToggle() {
  const { mode, toggle } = useThemeMode();
  return (
    <Pressable onPress={toggle} hitSlop={10} style={{ marginRight: 16 }} accessibilityLabel="Switch light or dark theme">
      <Ionicons name={mode === 'dark' ? 'sunny-outline' : 'moon-outline'} size={22} color={C.text} />
    </Pressable>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerRight: () => <ThemeToggle />,
        headerStyle: { backgroundColor: C.bg },
        headerTintColor: C.text,
        headerTitleStyle: { fontFamily: F.serif, fontSize: 22 },
        headerShadowVisible: false,
        tabBarStyle: { backgroundColor: C.bg, borderTopColor: C.line, height: 62, paddingTop: 6 },
        tabBarLabelStyle: { fontSize: 11 },
        tabBarActiveTintColor: C.accent,
        tabBarInactiveTintColor: C.faint,
        sceneStyle: { backgroundColor: C.bg },
      }}>
      <Tabs.Screen name="index" options={{ title: 'Feed', headerTitle: 'FINN', headerTitleStyle: { fontFamily: F.serif, fontSize: 24, fontWeight: '700', color: C.text }, tabBarIcon: icon('newspaper-outline', 'newspaper') }} />
      <Tabs.Screen name="watch" options={{ title: 'Watch', tabBarIcon: icon('eye-outline', 'eye') }} />
      <Tabs.Screen name="portfolio" options={{ title: 'Portfolio', tabBarIcon: icon('pie-chart-outline', 'pie-chart') }} />
    </Tabs>
  );
}
