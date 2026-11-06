import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { waitlistApi } from '../../api/endpoints';
import { runAction, type ActionResult } from '../../api/errors';
import { bookFromDto } from '../../api/mappers';
import type { Book } from '../types';
import { useAuth } from './AuthContext';

export interface WaitlistEntry {
  book: Book;
  createdAt: string;
}

interface WaitlistContextType {
  entries: WaitlistEntry[];
  /** Waiting is per title: any copy of it counts. */
  isWaiting: (book: { id: string; groupId?: string }) => boolean;
  /** Email me when this book is available again. */
  join: (bookId: string) => Promise<ActionResult>;
  leave: (bookId: string) => Promise<ActionResult>;
}

const WaitlistContext = createContext<WaitlistContextType | undefined>(undefined);

export function WaitlistProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [entries, setEntries] = useState<WaitlistEntry[]>([]);

  const load = useCallback(async () => {
    const dtos = await waitlistApi.list();
    setEntries(dtos.map((dto) => ({ book: bookFromDto(dto.book), createdAt: dto.created_at })));
  }, []);

  useEffect(() => {
    if (user) load().catch(() => setEntries([]));
    else setEntries([]);
  }, [user, load]);

  const waiting = useMemo(
    () => new Set(entries.flatMap((entry) => [entry.book.id, entry.book.groupId ?? entry.book.id])),
    [entries],
  );

  const join = (bookId: string) =>
    runAction(async () => {
      await waitlistApi.join(bookId);
      await load();
    });

  const leave = (bookId: string) =>
    runAction(async () => {
      await waitlistApi.leave(bookId); // the server clears the whole title
      await load();
    });

  return (
    <WaitlistContext.Provider value={{
        entries,
        isWaiting: (book) => waiting.has(book.id) || (!!book.groupId && waiting.has(book.groupId)),
        join,
        leave,
      }}>
      {children}
    </WaitlistContext.Provider>
  );
}

export function useWaitlist() {
  const context = useContext(WaitlistContext);
  if (!context) throw new Error('useWaitlist must be used within WaitlistProvider');
  return context;
}
