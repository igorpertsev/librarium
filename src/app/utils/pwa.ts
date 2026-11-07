import { useEffect, useState } from 'react';

/** Chrome's "install this app" event (not in TypeScript's DOM types). */
interface InstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

let deferred: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault(); // offer it from the settings instead of the browser's banner
    deferred = event as InstallPromptEvent;
    listeners.forEach((notify) => notify());
  });
  window.addEventListener('appinstalled', () => {
    deferred = null;
    listeners.forEach((notify) => notify());
  });
}

/** Whether the browser offers to install the app, and a function that asks it to. */
export function useInstallPrompt(): { canInstall: boolean; install: () => Promise<void> } {
  const [canInstall, setCanInstall] = useState(deferred !== null);
  useEffect(() => {
    const update = () => setCanInstall(deferred !== null);
    listeners.add(update);
    return () => {
      listeners.delete(update);
    };
  }, []);
  return {
    canInstall,
    install: async () => {
      if (!deferred) return;
      await deferred.prompt();
      await deferred.userChoice;
      deferred = null;
      listeners.forEach((notify) => notify());
    },
  };
}

/** Whether the browser is online (updates when the connection comes and goes). */
export function useOnline(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine));
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  return online;
}
