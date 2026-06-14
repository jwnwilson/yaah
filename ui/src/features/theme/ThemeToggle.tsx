import { IconButton } from "../../ui/IconButton";
import { useTheme } from "./useTheme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const toLight = theme === "dark";
  return (
    <IconButton label={toLight ? "Switch to light theme" : "Switch to dark theme"} onClick={toggle}>
      <span aria-hidden="true">{toLight ? "☀️" : "🌙"}</span>
    </IconButton>
  );
}
