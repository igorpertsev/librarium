import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock } from 'lucide-react';
import { toast } from 'sonner';
import { useReservations } from '../contexts/ReservationsContext';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';

const MAX_DAYS_AHEAD = 90;

/** YYYY-MM-DD of the reader's calendar day `offset` days from today. */
function localDay(offset: number): string {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

/** Book dialog: reserve the title for a day (e.g. the holidays), or cancel that reservation. */
export function ReserveAhead({ bookId, groupId, title }: { bookId: string; groupId?: string; title: string }) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const { reservationFor, reserve, cancel } = useReservations();
  const reservation = reservationFor({ id: bookId, groupId });
  const [open, setOpen] = useState(false);
  const [day, setDay] = useState('');
  const [busy, setBusy] = useState(false);

  const run = async (action: () => ReturnType<typeof reserve>, done: string) => {
    setBusy(true);
    const result = await action();
    setBusy(false);
    if (result.ok) {
      toast.success(done);
      setOpen(false);
      setDay('');
    } else {
      toast.error(errorMessage(t, result.error));
    }
  };

  if (reservation) {
    return (
      <div className="flex flex-wrap items-center justify-center gap-2 text-sm" data-testid="reserve-ahead">
        <CalendarClock className="w-4 h-4 text-primary" aria-hidden="true" />
        <span>{t('reserve.reservedFrom', { date: fmt.date(reservation.startsOn) })}</span>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => run(() => cancel(reservation.id), t('reserve.cancelled', { title }))}
        >
          {t('reserve.cancel')}
        </Button>
      </div>
    );
  }

  if (!open) {
    return (
      <div className="flex justify-center" data-testid="reserve-ahead">
        <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
          <CalendarClock className="w-4 h-4 mr-2" aria-hidden="true" />
          {t('reserve.open')}
        </Button>
      </div>
    );
  }

  return (
    <form
      className="space-y-2 rounded-md border border-border p-3"
      data-testid="reserve-ahead"
      onSubmit={(e) => {
        e.preventDefault();
        if (day) void run(() => reserve(bookId, day), t('reserve.done', { title, date: fmt.date(day) }));
      }}
    >
      <Label htmlFor="reserve-day">{t('reserve.from')}</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          id="reserve-day"
          type="date"
          required
          min={localDay(1)}
          max={localDay(MAX_DAYS_AHEAD)}
          value={day}
          onChange={(e) => setDay(e.target.value)}
          className="w-auto"
        />
        <Button type="submit" disabled={!day || busy}>
          {t('reserve.submit')}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
          {t('common.cancel')}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t('reserve.explain', { count: MAX_DAYS_AHEAD })}</p>
    </form>
  );
}
