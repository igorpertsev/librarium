import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ScanLine } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { orderFromDto } from '../../api/mappers';
import type { DeskCopyDto } from '../../api/types';
import type { Order } from '../types';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { copyIdFrom } from '../utils/labels';
import { IsbnScanner } from './IsbnScanner';
import { ReturnDialog } from './ReturnDialog';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';

/** Admin: scan a copy's label (camera, a USB scanner typing into the field, or a pasted link)
 * to see where it stands and hand over or take back its order. */
export function ScanDesk() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const inputRef = useRef<HTMLInputElement>(null);
  const [typed, setTyped] = useState('');
  const [scanning, setScanning] = useState(false);
  const [copy, setCopy] = useState<DeskCopyDto | null>(null);
  const [returning, setReturning] = useState<Order | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const look = async (copyId: string) => {
    const result = await runAction(() => adminApi.copyAtDesk(copyId));
    if (result.ok) setCopy(result.data);
    else {
      setCopy(null);
      toast.error(errorMessage(t, result.error));
    }
  };

  const submit = () => {
    const copyId = copyIdFrom(typed);
    setTyped('');
    if (copyId) void look(copyId);
    else toast.error(t('desk.notALabel'));
  };

  const handOver = async (orderId: string) => {
    setBusy(true);
    const result = await runAction(() => adminApi.setOrderStatus(orderId, 'confirmed'));
    setBusy(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    toast.success(t('desk.handedOver', { number: result.data.number }));
    if (copy) await look(copy.book.id);
  };

  const startReturn = async (orderId: string) => {
    const result = await runAction(() => adminApi.getOrder(orderId));
    if (result.ok) setReturning(orderFromDto(result.data));
    else toast.error(errorMessage(t, result.error));
  };

  const order = copy?.order ?? null;
  return (
    <div className="space-y-4 max-w-2xl">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="flex-1 min-w-56 space-y-2">
          <Label htmlFor="desk-code">{t('desk.scanField')}</Label>
          <Input id="desk-code" ref={inputRef} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </div>
        <Button type="submit" variant="outline" disabled={!typed.trim()}>{t('desk.look')}</Button>
        <Button type="button" onClick={() => setScanning(true)}>
          <ScanLine className="w-4 h-4 mr-1" aria-hidden="true" />
          {t('desk.camera')}
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">{t('desk.hint')}</p>

      {copy && (
        <section aria-labelledby="desk-copy" className="rounded-lg border border-border p-4 space-y-3" aria-live="polite">
          <div>
            <h2 id="desk-copy" className="text-lg">{copy.book.title}</h2>
            <p className="text-sm text-muted-foreground">{copy.book.author} · {copy.book.id.slice(0, 8)}</p>
          </div>
          {order === null ? (
            <p className="text-sm">{t('desk.onShelf')}</p>
          ) : order.status === 'pending' ? (
            <div className="space-y-2">
              <p className="text-sm">
                <Badge variant="outline" className="mr-2">#{order.number}</Badge>
                {t('desk.waiting', { name: order.reader_name, count: order.book_count })}
                {order.child_name && ` · ${t('family.forChild', { name: order.child_name })}`}
              </p>
              <Button onClick={() => handOver(order.id)} disabled={busy}>
                {t('desk.handOver', { number: order.number })}
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-sm">
                <Badge variant="outline" className="mr-2">#{order.number}</Badge>
                {t('desk.onLoan', { name: order.reader_name, date: fmt.date(order.due_date) })}
              </p>
              <Button onClick={() => startReturn(order.id)} disabled={busy}>
                {t('desk.takeBack', { number: order.number })}
              </Button>
            </div>
          )}
          {copy.held_for && copy.held_until && (
            <p className="text-sm">{t('desk.heldFor', { name: copy.held_for, date: fmt.dateTime(copy.held_until) })}</p>
          )}
        </section>
      )}

      <IsbnScanner open={scanning} mode="label" onClose={() => setScanning(false)} onDetected={(copyId) => void look(copyId)} />
      <ReturnDialog
        order={returning}
        onClose={() => setReturning(null)}
        onReturn={async (back) => {
          const result = await runAction(() => adminApi.setOrderStatus(back.id, 'returned'));
          setReturning(null);
          if (!result.ok) {
            toast.error(errorMessage(t, result.error));
            return;
          }
          toast.success(t('desk.takenBack', { number: result.data.number }));
          if (copy) await look(copy.book.id);
        }}
      />
    </div>
  );
}
