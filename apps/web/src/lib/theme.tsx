"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";

export type Theme = "light" | "dark" | "system";
type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "nc-theme";

type Listener = () => void;

const themeListeners = new Set<Listener>();
let cachedTheme: Theme | null = null;

function getStoredTheme(): Theme {
  if (cachedTheme === null) {
    cachedTheme = (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? "system";
  }
  return cachedTheme;
}

function getServerTheme(): Theme {
  return "system";
}

function writeStoredTheme(next: Theme) {
  cachedTheme = next;
  localStorage.setItem(STORAGE_KEY, next);
  themeListeners.forEach((listener) => listener());
}

function subscribeToStoredTheme(listener: Listener) {
  themeListeners.add(listener);
  return () => themeListeners.delete(listener);
}

function getSystemTheme(): ResolvedTheme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getServerSystemTheme(): ResolvedTheme {
  return "dark";
}

function subscribeToSystemTheme(listener: Listener) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", listener);
  return () => mq.removeEventListener("change", listener);
}

function applyTheme(resolved: ResolvedTheme) {
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

const ThemeContext = createContext<{
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
} | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(subscribeToStoredTheme, getStoredTheme, getServerTheme);
  const systemPref = useSyncExternalStore(
    subscribeToSystemTheme,
    getSystemTheme,
    getServerSystemTheme,
  );
  const resolvedTheme = theme === "system" ? systemPref : theme;

  // Sync the resolved theme to the DOM; this is a side effect on an external
  // system (the document class), not derived React state, so it belongs here.
  useEffect(() => {
    applyTheme(resolvedTheme);
  }, [resolvedTheme]);

  const setTheme = useCallback((next: Theme) => {
    writeStoredTheme(next);
  }, []);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme }),
    [theme, resolvedTheme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

/** Inline, blocking script so the correct theme class is set before first paint. */
export const themeInitScript = `(function(){try{var t=localStorage.getItem('${STORAGE_KEY}')||'system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;
