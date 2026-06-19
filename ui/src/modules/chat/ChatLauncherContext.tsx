import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface ChatLauncher {
  open: boolean;
  dictate: boolean; // request to auto-start dictation when the chat opens
  listening: boolean; // dictation is actively capturing speech (surfaced on the global mic)
  openChat: (dictate?: boolean) => void;
  toggle: () => void;
  close: () => void;
  consumeDictate: () => void; // ChatRail calls this once it has acted on `dictate`
  setListening: (v: boolean) => void; // ChatRail reports its dictation listening state here
}
const Ctx = createContext<ChatLauncher | null>(null);

export function ChatLauncherProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [dictate, setDictate] = useState(false);
  const [listening, setListening] = useState(false);
  const openChat = useCallback((d = false) => {
    setOpen(true);
    setDictate(d);
  }, []);
  const close = useCallback(() => {
    setOpen(false);
    setDictate(false);
  }, []);
  const toggle = useCallback(() => {
    setDictate(false);
    setOpen((o) => !o);
  }, []);
  const consumeDictate = useCallback(() => setDictate(false), []);
  const value = useMemo(
    () => ({ open, dictate, listening, openChat, toggle, close, consumeDictate, setListening }),
    [open, dictate, listening, openChat, toggle, close, consumeDictate],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChatLauncher(): ChatLauncher {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useChatLauncher must be used within ChatLauncherProvider");
  return ctx;
}
