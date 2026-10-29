/**
 * Light / dark theme, chosen by the user and kept on this device only.
 *
 * The whole app is painted from the CSS custom properties in styles.css, so a
 * theme is nothing more than which value the `data-theme` attribute resolves
 * them to. The choice lives in localStorage (never the server - it is a display
 * preference, not a record), defaults to following the OS, and is applied before
 * React renders so there is no flash of the wrong colours on load.
 */
export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "lifesmart.theme";

export const THEME_MODES: { value: ThemeMode; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

/** The saved mode, or "system" when the user has never chosen one. */
export function getStoredMode(): ThemeMode {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "light" || value === "dark" || value === "system") return value;
  } catch {
    // Storage can be unavailable (private mode); fall through to the default.
  }
  return "system";
}

function systemPrefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

/** Collapse a mode to the concrete theme the CSS switches on. */
export function resolveMode(mode: ThemeMode): "light" | "dark" {
  return mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
}

/** Paint the chosen mode without recording it (used on startup and on an
 *  OS-level change while the user is following the system). */
export function applyMode(mode: ThemeMode): void {
  if (typeof document === "undefined") return;
  const effective = resolveMode(mode);
  const root = document.documentElement;
  root.setAttribute("data-theme", effective);
  root.style.colorScheme = effective;
}

/** Remember the choice and apply it immediately. */
export function saveMode(mode: ThemeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // A failed write only means the choice will not survive a reload; applying
    // it still works for this session.
  }
  applyMode(mode);
}
