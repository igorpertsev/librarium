import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock } from 'lucide-react';
import { adminApi } from '../../api/endpoints';
import type { UpcomingReservationDto } from '../../api/types';
import { useFormat } from '../utils/format';

/** Admin orders tab: copies readers reserved for a day, soonest first (hidden when none). */
export function UpcomingReservations() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const [items, setItems] = useState<UpcomingReservationDto[]>([]);

  useEffect(() => {
    adminApi.upcomingReservations().then(setItems, () => setItems([]));
  }, []);

  if (items.length === 0) return null;
  return (
    <details className="mb-4 rounded-md border border-border p-3" data-testid="upcoming-reservations">
      <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
        <CalendarClock className="w-4 h-4" aria-hidden="true" />
        {t('reserve.upcoming', { count: items.length })}
      </summary>
      <ul className="mt-2 space-y-1 text-sm">
        {items.map((item) => (
          <li key={item.id} className="flex flex-wrap gap-x-2">
            <span className="font-medium tabular-nums">{fmt.date(item.starts_on)}</span>
            <span>{item.title}</span>
            <span className="text-muted-foreground">— {item.author}</span>
            <span className="text-muted-foreground">· {item.reader_name} ({item.reader_email})</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
