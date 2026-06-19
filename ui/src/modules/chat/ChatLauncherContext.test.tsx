import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, test } from "vitest";
import { ChatLauncherProvider, useChatLauncher } from "./ChatLauncherContext";

function wrapper({ children }: { children: ReactNode }) {
  return <ChatLauncherProvider>{children}</ChatLauncherProvider>;
}

test("openChat(true) sets open and dictate", () => {
  const { result } = renderHook(() => useChatLauncher(), { wrapper });

  act(() => result.current.openChat(true));

  expect(result.current.open).toBe(true);
  expect(result.current.dictate).toBe(true);
});

test("openChat() defaults dictate to false", () => {
  const { result } = renderHook(() => useChatLauncher(), { wrapper });

  act(() => result.current.openChat());

  expect(result.current.open).toBe(true);
  expect(result.current.dictate).toBe(false);
});

test("toggle flips open and clears dictate", () => {
  const { result } = renderHook(() => useChatLauncher(), { wrapper });

  act(() => result.current.openChat(true));
  act(() => result.current.toggle());

  expect(result.current.open).toBe(false);
  expect(result.current.dictate).toBe(false);

  act(() => result.current.toggle());
  expect(result.current.open).toBe(true);
  expect(result.current.dictate).toBe(false);
});

test("consumeDictate clears dictate without closing", () => {
  const { result } = renderHook(() => useChatLauncher(), { wrapper });

  act(() => result.current.openChat(true));
  act(() => result.current.consumeDictate());

  expect(result.current.open).toBe(true);
  expect(result.current.dictate).toBe(false);
});

test("close clears open and dictate", () => {
  const { result } = renderHook(() => useChatLauncher(), { wrapper });

  act(() => result.current.openChat(true));
  act(() => result.current.close());

  expect(result.current.open).toBe(false);
  expect(result.current.dictate).toBe(false);
});

test("useChatLauncher throws outside a provider", () => {
  expect(() => renderHook(() => useChatLauncher())).toThrow(
    /must be used within ChatLauncherProvider/,
  );
});
