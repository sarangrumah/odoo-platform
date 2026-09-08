"use client";

// Three states, matching how the CSS is written: "system" stamps nothing and
// lets prefers-color-scheme decide; light/dark stamp data-theme so the choice
// beats the OS in both directions.

import { useEffect, useState } from "react";

type Theme = "system" | "light" | "dark";
const KEY = "cockpit-theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    const stored = window.localStorage.getItem(KEY) as Theme | null;
    if (stored === "light" || stored === "dark") setTheme(stored);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") {
      root.removeAttribute("data-theme");
      window.localStorage.removeItem(KEY);
    } else {
      root.setAttribute("data-theme", theme);
      window.localStorage.setItem(KEY, theme);
    }
  }, [theme]);

  const next: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
  const label: Record<Theme, string> = { system: "Auto", light: "Terang", dark: "Gelap" };

  return (
    <button
      type="button"
      className="btn"
      onClick={() => setTheme(next[theme])}
      title="Ganti tema (auto → terang → gelap)"
    >
      {label[theme]}
    </button>
  );
}
