import { createContext, useContext, useState, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import { applyTheme } from './theme';

type Mode = 'dark' | 'light';
const Ctx = createContext<{ mode: Mode; toggle: () => void }>({ mode: 'dark', toggle: () => {} });

/** Starts from the phone's setting; the header button flips it. */
export function ThemeProvider({ children }: { children: (mode: Mode) => ReactNode }) {
  const system = useColorScheme();
  const [mode, setMode] = useState<Mode>(system === 'light' ? 'light' : 'dark');
  applyTheme(mode); // copy the palette into C before anything below renders
  return <Ctx.Provider value={{ mode, toggle: () => setMode((m) => (m === 'dark' ? 'light' : 'dark')) }}>{children(mode)}</Ctx.Provider>;
}

export const useThemeMode = () => useContext(Ctx);
