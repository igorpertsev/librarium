import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { toast } from 'sonner';
import { errorMessage } from '../utils/apiErrors';
import type { CopyCondition, Order } from '../types';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';

const CONDITIONS: CopyCondition[] = ['new', 'good', 'worn', 'damaged'];
const SELECT = 'border border-border rounded-md px-2 py-1.5 text-sm bg-background';

interface Draft {
  condition: CopyCondition;
  note: string;
}

/**
 * Admin: mark an order returned, noting how each copy came back. Only changed copies are
 * saved; the order is marked returned afterwards.
 */
export function ReturnDialog({
  order,
  onClose,
  onReturn,
}: {
  order: Order | null;
  onClose: () => void;
  onReturn: (order: Order) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!order) return;
    setDrafts(
      Object.fromEntries(
        order.books.map((book) => [book.id, { condition: book.condition ?? 'good', note: book.conditionNote ?? '' }]),
      ),
    );
  }, [order]);

  const save = async () => {
    if (!order) return;
    setBusy(true);
    const changed = order.books.filter((book) => {
      const draft = drafts[book.id];
      return draft && (draft.condition !== (book.condition ?? 'good') || draft.note.trim() !== (book.conditionNote ?? ''));
    });
    const noted = await runAction(async () => {
      for (const book of changed) {
        const draft = drafts[book.id];
        await adminApi.updateBook(book.id, { condition: draft.condition, condition_note: draft.note.trim() || null });
      }
    });
    if (noted.ok) await onReturn(order);
    else toast.error(errorMessage(t, noted.error));
    setBusy(false);
  };

  return (
    <Dialog open={order !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('condition.returnTitle')}</DialogTitle>
          <DialogDescription>{t('condition.returnHint')}</DialogDescription>
        </DialogHeader>
        <ul className="space-y-4">
          {order?.books.map((book) => {
            const draft = drafts[book.id] ?? { condition: 'good', note: '' };
            return (
              <li key={book.id} className="space-y-2">
                <p className="text-sm font-medium">{book.title}</p>
                <div className="flex flex-wrap gap-2">
                  <select
                    aria-label={t('condition.of', { title: book.title })}
                    className={SELECT}
                    value={draft.condition}
                    onChange={(e) => setDrafts({ ...drafts, [book.id]: { ...draft, condition: e.target.value as CopyCondition } })}
                  >
                    {CONDITIONS.map((condition) => (
                      <option key={condition} value={condition}>
                        {t(`condition.${condition}`)}
                      </option>
                    ))}
                  </select>
                  <Label className="sr-only" htmlFor={`note-${book.id}`}>
                    {t('condition.noteOf', { title: book.title })}
                  </Label>
                  <Input
                    id={`note-${book.id}`}
                    className="flex-1 min-w-[10rem]"
                    maxLength={300}
                    placeholder={t('condition.notePlaceholder')}
                    value={draft.note}
                    onChange={(e) => setDrafts({ ...drafts, [book.id]: { ...draft, note: e.target.value } })}
                  />
                </div>
              </li>
            );
          })}
        </ul>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={save} disabled={busy}>
            {t('admin.markReturned')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
