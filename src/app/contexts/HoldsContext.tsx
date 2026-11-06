import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { usersApi } from '../../api/endpoints';
import { runAction, type ActionResult } from '../../api/errors';
import { bookFromDto } from '../../api/mappers';
import type { Book } from '../types';
import { useAuth } from './AuthContext';
import { useCatalog } from './CatalogContext';

export interface Hold {
  /** The held copy: only this reader can add it to the cart. */
  book: Book;
  heldUntil: string;
}

interface HoldsContextType {
  holds: Hold[];
  /** The reader's hold on any copy of this title, if they have one. */
  holdFor: (book: { id: string; groupId?: string }) => Hold | undefined;
  release: (bookId: string) => Promise<ActionResult>;
}

const HoldsContext = createContext<HoldsContextType | undefined>(undefined);

export function HoldsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { version, invalidateCatalog } = useCatalog();
  const [holds, setHolds] = useState<Hold[]>([]);

  const load = useCallback(async () => {
    const dtos = await usersApi.holds();
    setHolds(dtos.map((dto) => ({ book: bookFromDto(dto.book), heldUntil: dto.held_until })));
  }, []);

  useEffect(() => {
    if (user) load().catch(() => setHolds([]));
    else setHolds([]);
  }, [user, load, version]);

  const byTitle = useMemo(
    () => new Map(holds.flatMap((hold) => [[hold.book.id, hold], [hold.book.groupId ?? hold.book.id, hold]])),
    [holds],
  );

  const release = (bookId: string) =>
    runAction(async () => {
      await usersApi.releaseHold(bookId);
      invalidateCatalog(); // the copy goes to the next reader
    });

  return (
    <HoldsContext.Provider
      value={{
        holds,
        holdFor: (book) => byTitle.get(book.id) ?? (book.groupId ? byTitle.get(book.groupId) : undefined),
        release,
      }}
    >
      {children}
    </HoldsContext.Provider>
  );
}

export function useHolds() {
  const context = useContext(HoldsContext);
  if (!context) throw new Error('useHolds must be used within HoldsProvider');
  return context;
}
