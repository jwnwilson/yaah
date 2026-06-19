import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface ChatLauncher {
  open: boolean;
  dictate: boolean; // request to auto-start dictation when the chat opens
  openChat: (dictate?: boolean) => void;
  toggle: () => void;
  close: () => void;
  consumeDictate: () => void; // ChatRail calls this once it has acted on `dictate`
}
const Ctx = createContext<ChatLauncher | null>(null);

export function ChatLauncherProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [dictate, setDictate] = useState(false);
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
    () => ({ open, dictate, openChat, toggle, close, consumeDictate }),
    [open, dictate, openChat, toggle, close, consumeDictate],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useChatLauncher(): ChatLauncher {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useChatLauncher must be used within ChatLauncherProvider");
  return ctx;
}
