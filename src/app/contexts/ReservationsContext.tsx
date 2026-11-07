import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { usersApi } from '../../api/endpoints';
import { runAction, type ActionResult } from '../../api/errors';
import { bookFromDto } from '../../api/mappers';
import type { Book } from '../types';
import { useAuth } from './AuthContext';
import { useCatalog } from './CatalogContext';

export interface Reservation {
  id: string;
  /** The copy set aside for the reader. */
  book: Book;
  /** The day the reader wants the book from (YYYY-MM-DD). */
  startsOn: string;
}

interface ReservationsContextType {
  reservations: Reservation[];
  /** The reader's reservation of any copy of this title, if they have one. */
  reservationFor: (book: { id: string; groupId?: string }) => Reservation | undefined;
  reserve: (bookId: string, startsOn: string) => Promise<ActionResult>;
  cancel: (reservationId: string) => Promise<ActionResult>;
}

const ReservationsContext = createContext<ReservationsContextType | undefined>(undefined);

export function ReservationsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { version, invalidateCatalog } = useCatalog();
  const [reservations, setReservations] = useState<Reservation[]>([]);

  const load = useCallback(async () => {
    const dtos = await usersApi.reservations();
    setReservations(dtos.map((dto) => ({ id: dto.id, book: bookFromDto(dto.book), startsOn: dto.starts_on })));
  }, []);

  useEffect(() => {
    if (user) load().catch(() => setReservations([]));
    else setReservations([]);
  }, [user, load, version]);

  const byTitle = useMemo(
    () =>
      new Map(
        reservations.flatMap((r) => [
          [r.book.id, r],
          [r.book.groupId ?? r.book.id, r],
        ]),
      ),
    [reservations],
  );

  // Both change which copies others can borrow, so the catalogue is reloaded too.
  const reserve = (bookId: string, startsOn: string) =>
    runAction(async () => {
      await usersApi.reserve(bookId, startsOn);
      invalidateCatalog();
    });
  const cancel = (reservationId: string) =>
    runAction(async () => {
      await usersApi.cancelReservation(reservationId);
      invalidateCatalog();
    });

  return (
    <ReservationsContext.Provider
      value={{
        reservations,
        reservationFor: (book) =>
          byTitle.get(book.id) ?? (book.groupId ? byTitle.get(book.groupId) : undefined),
        reserve,
        cancel,
      }}
    >
      {children}
    </ReservationsContext.Provider>
  );
}

export function useReservations() {
  const context = useContext(ReservationsContext);
  if (!context) throw new Error('useReservations must be used within ReservationsProvider');
  return context;
}
