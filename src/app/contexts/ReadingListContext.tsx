import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { readingListApi } from '../../api/endpoints';
import { runAction, type ActionResult } from '../../api/errors';
import { bookFromDto } from '../../api/mappers';
import type { Book } from '../types';
import { useAuth } from './AuthContext';
import { useCatalog } from './CatalogContext';

export interface ReadingListItem {
  /** The copy of the title that can be borrowed now, if there is one. */
  book: Book;
  addedAt: string;
}

interface ReadingListContextType {
  items: ReadingListItem[];
  /** Per title: any copy of it counts. */
  has: (book: { id: string; groupId?: string }) => boolean;
  add: (bookId: string) => Promise<ActionResult>;
  remove: (bookId: string) => Promise<ActionResult>;
}

const ReadingListContext = createContext<ReadingListContextType | undefined>(undefined);

export function ReadingListProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { version } = useCatalog();
  const [items, setItems] = useState<ReadingListItem[]>([]);

  const load = useCallback(async () => {
    const dtos = await readingListApi.list();
    setItems(dtos.map((dto) => ({ book: bookFromDto(dto.book), addedAt: dto.created_at })));
  }, []);

  // Availability shown on the list changes with orders, so reload with the catalogue.
  useEffect(() => {
    if (user) load().catch(() => setItems([]));
    else setItems([]);
  }, [user, load, version]);

  const titles = useMemo(
    () => new Set(items.flatMap((item) => [item.book.id, item.book.groupId ?? item.book.id])),
    [items],
  );

  const add = (bookId: string) =>
    runAction(async () => {
      await readingListApi.add(bookId);
      await load();
    });

  const remove = (bookId: string) =>
    runAction(async () => {
      await readingListApi.remove(bookId);
      await load();
    });

  return (
    <ReadingListContext.Provider
      value={{
        items,
        has: (book) => titles.has(book.id) || (!!book.groupId && titles.has(book.groupId)),
        add,
        remove,
      }}
    >
      {children}
    </ReadingListContext.Provider>
  );
}

export function useReadingList() {
  const context = useContext(ReadingListContext);
  if (!context) throw new Error('useReadingList must be used within ReadingListProvider');
  return context;
}
