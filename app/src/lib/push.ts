import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { api } from './api';

if (Platform.OS !== 'web')
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldPlaySound: true,
      shouldSetBadge: false,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });

export type PushStatus = { ok: boolean; message: string; token?: string };
let last: PushStatus = { ok: false, message: 'Not registered yet' };
export const lastPushStatus = () => last;

/** Ask permission, get the Expo push token, register it with the backend.
 *  Works on real phones and on emulators that have Google Play services. */
export async function registerForPush(): Promise<PushStatus> {
  if (Platform.OS === 'web') return (last = { ok: false, message: 'Push needs the Android app (not available on web)' });
  try {
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'FINN alerts',
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#E5484D',
      });
    }
    const { status: existing } = await Notifications.getPermissionsAsync();
    let status = existing;
    if (existing !== 'granted') status = (await Notifications.requestPermissionsAsync()).status;
    if (status !== 'granted') return (last = { ok: false, message: 'Notification permission is off. Turn it on in Settings → Apps → FINN.' });
    const projectId = Constants?.expoConfig?.extra?.eas?.projectId ?? Constants?.easConfig?.projectId;
    if (!projectId) return (last = { ok: false, message: 'No EAS projectId in app config' });
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    await api.registerPush(token, Platform.OS);
    return (last = { ok: true, message: 'Registered for push', token });
  } catch (e: any) {
    console.warn('push registration failed', e);
    return (last = { ok: false, message: `Push registration failed: ${e?.message || e}` });
  }
}
