import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ThumbsUp } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { PurchaseRequestDto, PurchaseStatusDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { Button } from './ui/button';
import { Input } from './ui/input';

const STATUSES: PurchaseStatusDto[] = ['open', 'ordered', 'added', 'declined'];
const SELECT = 'border border-border rounded-md px-2 py-1.5 text-sm bg-background';

/** Admin: readers' suggestions, most votes first; mark them ordered, added or declined. */
export function PurchaseRequestsTab() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const [items, setItems] = useState<PurchaseRequestDto[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const list = await adminApi.purchaseRequests().catch(() => []);
    setItems(list);
    setNotes(Object.fromEntries(list.map((item) => [item.id, item.librarian_note ?? ''])));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (item: PurchaseRequestDto, change: { status?: PurchaseStatusDto; librarian_note?: string | null }) => {
    const result = await runAction(() => adminApi.updatePurchaseRequest(item.id, change));
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    toast.success(change.status === 'added' ? t('suggest.addedToast', { title: item.title }) : t('suggest.saved'));
    setItems((current) => current?.map((x) => (x.id === item.id ? result.data : x)) ?? current);
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg">{t('suggest.adminTitle')}</h2>
        <p className="text-sm text-muted-foreground">{t('suggest.adminDescription')}</p>
      </div>
      {items === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">{t('suggest.empty')}</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.id} className="rounded-lg border border-border p-3 space-y-2">
              <div className="flex flex-wrap items-start gap-3">
                <span className="inline-flex items-center gap-1 text-sm tabular-nums" title={t('suggest.votes', { count: item.votes })}>
                  <ThumbsUp className="w-4 h-4" aria-hidden="true" />
                  <span className="sr-only">{t('suggest.votes', { count: item.votes })}</span>
                  <span aria-hidden="true">{item.votes}</span>
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{item.title}</p>
                  <p className="text-sm text-muted-foreground">
                    {item.author}
                    {item.isbn && ` · ISBN ${item.isbn}`}
                    {' · '}
                    {fmt.date(item.created_at)}
                  </p>
                  {item.note && <p className="text-sm mt-1">{item.note}</p>}
                </div>
                <select
                  aria-label={t('suggest.statusOf', { title: item.title })}
                  className={SELECT}
                  value={item.status}
                  onChange={(e) => void save(item, { status: e.target.value as PurchaseStatusDto })}
                >
                  {STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {t(`suggest.status.${status}`)}
                    </option>
                  ))}
                </select>
              </div>
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void save(item, { librarian_note: notes[item.id]?.trim() || null });
                }}
              >
                <Input
                  aria-label={t('suggest.noteFor', { title: item.title })}
                  placeholder={t('suggest.notePlaceholder')}
                  maxLength={500}
                  value={notes[item.id] ?? ''}
                  onChange={(e) => setNotes({ ...notes, [item.id]: e.target.value })}
                />
                <Button type="submit" variant="outline" size="sm">
                  {t('suggest.saveNote')}
                </Button>
              </form>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
