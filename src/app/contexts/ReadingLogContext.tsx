import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { usersApi } from '../../api/endpoints';
import { runAction, type ActionResult } from '../../api/errors';
import { bookFromDto } from '../../api/mappers';
import type { BadgeDto } from '../../api/types';
import type { Book } from '../types';
import { useAuth } from './AuthContext';
import { useCatalog } from './CatalogContext';
import { useFamily } from './FamilyContext';

export interface ReadingLog {
  entries: { book: Book; finishedOn: string }[];
  total: number;
  thisYear: number;
  badges: BadgeDto[];
  /** Borrowed titles not in the log yet. */
  toLog: Book[];
}

interface ReadingLogContextType {
  /** Whose log is shown and marked: the reader (null) or one of their children. */
  profile: string | null;
  setProfile: (childId: string | null) => void;
  log: ReadingLog | null;
  /** Per title: any copy of it counts. */
  isFinished: (book: { id: string; groupId?: string }) => boolean;
  markFinished: (bookId: string, finishedOn?: string) => Promise<ActionResult>;
  unmark: (bookId: string) => Promise<ActionResult>;
}

const ReadingLogContext = createContext<ReadingLogContextType | undefined>(undefined);

export function ReadingLogProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { version } = useCatalog();
  const { children: kids } = useFamily();
  const [log, setLog] = useState<ReadingLog | null>(null);
  const storageKey = user ? `readingLogProfile:${user.id}` : null;
  const [chosen, setChosen] = useState<string | null>(null);
  // The chosen profile is remembered on this device (e.g. a child's tablet).
  useEffect(() => {
    if (!storageKey) return;
    try {
      setChosen(localStorage.getItem(storageKey));
    } catch {
      setChosen(null);
    }
  }, [storageKey]);
  const setProfile = (childId: string | null) => {
    setChosen(childId);
    if (!storageKey) return;
    try {
      if (childId) localStorage.setItem(storageKey, childId);
      else localStorage.removeItem(storageKey);
    } catch {
      /* private mode: only for this visit */
    }
  };
  // A removed child falls back to the reader's own log.
  const profile = chosen && kids.some((kid) => kid.id === chosen) ? chosen : null;

  const load = useCallback(async () => {
    const dto = await usersApi.readingLog(profile ?? undefined);
    setLog({
      entries: dto.entries.map((entry) => ({ book: bookFromDto(entry.book), finishedOn: entry.finished_on })),
      total: dto.total,
      thisYear: dto.this_year,
      badges: dto.badges,
      toLog: dto.to_log.map(bookFromDto),
    });
  }, [profile]);

  useEffect(() => {
    if (user) load().catch(() => setLog(null));
    else setLog(null);
  }, [user, load, version]);

  const titles = useMemo(
    () => new Set((log?.entries ?? []).flatMap(({ book }) => [book.id, book.groupId ?? book.id])),
    [log],
  );

  const markFinished = (bookId: string, finishedOn?: string) =>
    runAction(async () => {
      await usersApi.markFinished(bookId, finishedOn, profile ?? undefined);
      await load();
    });
  const unmark = (bookId: string) =>
    runAction(async () => {
      await usersApi.unmarkFinished(bookId, profile ?? undefined);
      await load();
    });

  return (
    <ReadingLogContext.Provider
      value={{
        profile,
        setProfile,
        log,
        isFinished: (book) => titles.has(book.id) || (!!book.groupId && titles.has(book.groupId)),
        markFinished,
        unmark,
      }}
    >
      {children}
    </ReadingLogContext.Provider>
  );
}

export function useReadingLog() {
  const context = useContext(ReadingLogContext);
  if (!context) throw new Error('useReadingLog must be used within ReadingLogProvider');
  return context;
}
