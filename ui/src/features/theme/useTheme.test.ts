import { act, renderHook } from "@testing-library/react";
import { useTheme } from "./useTheme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

test("defaults to dark and applies the dark class", () => {
  const { result } = renderHook(() => useTheme());
  expect(result.current.theme).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
});

test("toggle switches to light, removes class, and persists", () => {
  const { result } = renderHook(() => useTheme());
  act(() => result.current.toggle());
  expect(result.current.theme).toBe("light");
  expect(document.documentElement.classList.contains("dark")).toBe(false);
  expect(localStorage.getItem("yaah-theme")).toBe("light");
});
