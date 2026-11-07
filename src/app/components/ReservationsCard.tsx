import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useReservations } from '../contexts/ReservationsContext';
import { errorMessage } from '../utils/apiErrors';
import { useBookText } from '../utils/bookText';
import { coverOfSize } from '../utils/covers';
import { useFormat } from '../utils/format';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

/** Profile: titles the reader reserved for a day. */
export function ReservationsCard() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const textOf = useBookText();
  const { reservations, cancel } = useReservations();
  const [busy, setBusy] = useState<string | null>(null);

  if (reservations.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('reserve.title')}</CardTitle>
        <CardDescription>{t('reserve.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {reservations.map(({ id, book, startsOn }) => {
          const text = textOf(book);
          return (
            <div key={id} className="flex flex-wrap sm:flex-nowrap items-center gap-x-4 gap-y-2 p-3 border border-border rounded-lg">
              <div className="w-10 h-14 flex-shrink-0 overflow-hidden rounded bg-muted">
                <img src={coverOfSize(book.coverImage, 'S')} alt="" className="w-full h-full object-cover" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="truncate">{text.title}</h3>
                <p className="text-sm text-muted-foreground">{t('reserve.reservedFrom', { date: fmt.date(startsOn) })}</p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy === id}
                onClick={async () => {
                  setBusy(id);
                  const result = await cancel(id);
                  setBusy(null);
                  if (result.ok) toast.success(t('reserve.cancelled', { title: text.title }));
                  else toast.error(errorMessage(t, result.error));
                }}
              >
                {t('reserve.cancel')}
              </Button>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
