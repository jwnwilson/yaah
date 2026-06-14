import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const STORAGE_KEY = "yaah-theme";

function readStored(): Theme {
  try {
    // Any stored value other than "light" is treated as "dark" (so a future
    // "system" option is not silently coerced into a light/dark default here).
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readStored);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore unavailable storage */
    }
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return { theme, toggle };
}
