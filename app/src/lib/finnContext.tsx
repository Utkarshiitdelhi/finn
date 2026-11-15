import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

// What the FINN button knows about the screen you're on: "What did they say about margins?"
// needs no company name on a Company screen.
export interface ScreenCtx {
  screen: 'feed' | 'company' | 'filing' | 'watch' | 'portfolio' | 'impact';
  ticker?: string;
  filing_id?: string;
}

const Ctx = createContext<{ ctx: ScreenCtx; setCtx: (c: ScreenCtx) => void; bump: number; refresh: () => void }>({
  ctx: { screen: 'feed' },
  setCtx: () => {},
  bump: 0,
  refresh: () => {},
});

export function FinnProvider({ children }: { children: ReactNode }) {
  const [ctx, setCtx] = useState<ScreenCtx>({ screen: 'feed' });
  const [bump, setBump] = useState(0);
  return <Ctx.Provider value={{ ctx, setCtx, bump, refresh: () => setBump((b) => b + 1) }}>{children}</Ctx.Provider>;
}

export const useFinn = () => useContext(Ctx);

/** Call in a screen to tell the assistant where you are. */
export function useScreen(c: ScreenCtx) {
  const { setCtx } = useFinn();
  useEffect(() => {
    setCtx(c);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c.screen, c.ticker, c.filing_id]);
}
