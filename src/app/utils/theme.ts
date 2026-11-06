import { useSyncExternalStore } from 'react';

/** "system" follows the device (prefers-color-scheme). */
export type ThemePreference = 'system' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'theme';
const listeners = new Set<() => void>();

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches;
}

export function getThemePreference(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    return 'system';
  }
}

export function resolveTheme(preference = getThemePreference()): ResolvedTheme {
  return preference === 'dark' || (preference === 'system' && systemPrefersDark()) ? 'dark' : 'light';
}

/** Puts the `dark` class on <html> (the Tailwind dark variant and the theme tokens use it). */
export function applyTheme(): void {
  const theme = resolveTheme();
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.style.colorScheme = theme;
  listeners.forEach((listener) => listener());
}

export function setThemePreference(preference: ThemePreference): void {
  try {
    if (preference === 'system') localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Storage unavailable (private mode): the choice lasts until the page is reloaded.
  }
  applyTheme();
}

/** Call once at start-up: apply the theme and follow device changes while on "system". */
export function initTheme(): void {
  applyTheme();
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (getThemePreference() === 'system') applyTheme();
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): { preference: ThemePreference; resolved: ResolvedTheme } {
  const preference = useSyncExternalStore(subscribe, getThemePreference, () => 'system' as const);
  const resolved = useSyncExternalStore(subscribe, () => resolveTheme(), () => 'light' as const);
  return { preference, resolved };
}
