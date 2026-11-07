import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { usersApi } from '../../api/endpoints';
import { runAction, type ActionResult } from '../../api/errors';
import { bookFromDto } from '../../api/mappers';
import type { BadgeDto } from '../../api/types';
import type { Book } from '../types';
import { useAuth } from './AuthContext';
import { useCatalog } from './CatalogContext';

export interface ReadingLog {
  entries: { book: Book; finishedOn: string }[];
  total: number;
  thisYear: number;
  badges: BadgeDto[];
  /** Borrowed titles not in the log yet. */
  toLog: Book[];
}

interface ReadingLogContextType {
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
  const [log, setLog] = useState<ReadingLog | null>(null);

  const load = useCallback(async () => {
    const dto = await usersApi.readingLog();
    setLog({
      entries: dto.entries.map((entry) => ({ book: bookFromDto(entry.book), finishedOn: entry.finished_on })),
      total: dto.total,
      thisYear: dto.this_year,
      badges: dto.badges,
      toLog: dto.to_log.map(bookFromDto),
    });
  }, []);

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
      await usersApi.markFinished(bookId, finishedOn);
      await load();
    });
  const unmark = (bookId: string) =>
    runAction(async () => {
      await usersApi.unmarkFinished(bookId);
      await load();
    });

  return (
    <ReadingLogContext.Provider
      value={{
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
