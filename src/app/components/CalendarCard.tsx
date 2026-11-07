import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarDays, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { usersApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { useAuth } from '../contexts/AuthContext';
import { errorMessage } from '../utils/apiErrors';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';

/** Profile: a private calendar feed with due dates, pickups, held books and reservations. The
 * link is shown only right after it is made (only its hash is stored). */
export function CalendarCard() {
  const { t } = useTranslation();
  const { user, reloadUser } = useAuth();
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!user) return null;
  const exists = user.calendarFeed ?? false;

  const make = async () => {
    setBusy(true);
    const result = await runAction(() => usersApi.calendarLink());
    setBusy(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    setUrl(result.data.url);
    await reloadUser().catch(() => undefined);
  };

  const remove = async () => {
    setBusy(true);
    const result = await runAction(() => usersApi.calendarRemove());
    setBusy(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    setUrl(null);
    toast.success(t('calendar.removed'));
    await reloadUser().catch(() => undefined);
  };

  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      toast.success(t('calendar.copied'));
    } catch {
      toast.error(t('calendar.copyFailed'));
    }
  };

  return (
    <Card data-testid="calendar">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="w-5 h-5" aria-hidden="true" />
          {t('calendar.title')}
        </CardTitle>
        <CardDescription>{t('calendar.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {url && (
          <div className="space-y-2">
            <Label htmlFor="calendar-url">{t('calendar.link')}</Label>
            <div className="flex gap-2">
              <Input id="calendar-url" readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
              <Button type="button" variant="outline" onClick={copy} aria-label={t('calendar.copy')}>
                <Copy className="w-4 h-4" aria-hidden="true" />
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">{t('calendar.howTo')}</p>
            <Button asChild variant="outline">
              <a href={url.replace(/^https?:/, 'webcal:')}>{t('calendar.subscribe')}</a>
            </Button>
          </div>
        )}
        {!url && exists && <p className="text-sm">{t('calendar.exists')}</p>}
        <div className="flex flex-wrap gap-2">
          <Button onClick={make} disabled={busy}>
            {exists ? t('calendar.newLink') : t('calendar.makeLink')}
          </Button>
          {exists && (
            <Button variant="ghost" onClick={remove} disabled={busy}>
              {t('calendar.turnOff')}
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{t('calendar.private')}</p>
      </CardContent>
    </Card>
  );
}
