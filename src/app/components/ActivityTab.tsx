import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { adminApi } from '../../api/endpoints';
import type { AuditEventDto } from '../../api/types';
import { useFormat } from '../utils/format';
import { Button } from './ui/button';

const PAGE_SIZE = 50;

/** "status: confirmed · due_date: 2026-12-01" (nested values as JSON). */
function detailsText(details: AuditEventDto['details']): string {
  return Object.entries(details)
    .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(' · ');
}

/** Admin: changes made by staff, newest first. */
export function ActivityTab() {
  const { t, i18n } = useTranslation();
  const fmt = useFormat();
  const [events, setEvents] = useState<AuditEventDto[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (next: number) => {
    setLoading(true);
    try {
      const result = await adminApi.auditLog(next, PAGE_SIZE);
      setEvents((current) => (next === 1 ? result.items : [...current, ...result.items]));
      setTotal(result.total);
      setPage(next);
    } catch {
      setTotal((current) => current ?? 0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(1);
  }, [load]);

  const actionLabel = (event: AuditEventDto) => {
    const key = `audit.actions.${event.action}`;
    return i18n.exists(key) ? t(key) : `${event.method} ${event.path}`;
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg">{t('audit.title')}</h2>
          <p className="text-sm text-muted-foreground">{t('audit.description')}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => load(1)} disabled={loading}>
          {t('audit.refresh')}
        </Button>
      </div>
      {total === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">{t('audit.empty')}</p>
      ) : (
        <ol className="divide-y divide-border rounded-md border border-border" aria-label={t('audit.title')}>
          {events.map((event) => {
            const details = detailsText(event.details);
            return (
              <li key={event.id} className="px-4 py-3 text-sm space-y-0.5">
                <p className="flex flex-wrap gap-x-2">
                  <span className="font-medium">{actionLabel(event)}</span>
                  {event.entity_label && <span>— {event.entity_label}</span>}
                </p>
                <p className="text-xs text-muted-foreground">
                  {fmt.dateTime(event.created_at)} · {event.actor_email}
                </p>
                {details && <p className="text-xs text-muted-foreground break-words">{details}</p>}
              </li>
            );
          })}
        </ol>
      )}
      {total !== null && events.length < total && (
        <Button variant="outline" onClick={() => load(page + 1)} disabled={loading}>
          {t('audit.more')}
        </Button>
      )}
    </div>
  );
}
