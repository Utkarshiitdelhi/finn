import * as Notifications from 'expo-notifications';
import { router, Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { Platform, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { FinnButton } from '@/components/FinnButton';
import { FinnProvider } from '@/lib/finnContext';
import { registerForPush } from '@/lib/push';
import { ThemeProvider } from '@/lib/themeContext';
import { C, F } from '@/lib/theme';

/** Notifications deep-link straight to the card or company they are about (data.url = "/filing/<id>"). */
function NotificationLinks() {
  const last = Notifications.useLastNotificationResponse();
  useEffect(() => {
    const url = last?.notification.request.content.data?.url;
    if (typeof url === 'string' && last?.actionIdentifier === Notifications.DEFAULT_ACTION_IDENTIFIER) {
      router.push(url as any);
    }
  }, [last]);
  return null;
}

export default function RootLayout() {
  useEffect(() => {
    registerForPush();
  }, []);
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        {(mode) => (
          <FinnProvider>
            {/* key={mode}: remount on theme switch so every style re-reads the palette */}
            <View key={mode} style={{ flex: 1, backgroundColor: C.bg }}>
              <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
              {Platform.OS !== 'web' ? <NotificationLinks /> : null}
              <Stack
                screenOptions={{
                  headerStyle: { backgroundColor: C.bg },
                  headerTintColor: C.text,
                  headerTitleStyle: { fontFamily: F.serif },
                  contentStyle: { backgroundColor: C.bg },
                  headerShadowVisible: false,
                }}>
                <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                <Stack.Screen name="company/[ticker]" options={{ title: '' }} />
                <Stack.Screen name="filing/[id]" options={{ title: '' }} />
                <Stack.Screen name="impact/[series]" options={{ title: 'Impact', presentation: 'formSheet', sheetAllowedDetents: [0.6, 1] }} />
              </Stack>
              <FinnButton />
            </View>
          </FinnProvider>
        )}
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
