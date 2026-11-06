import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import type { ConfirmOptions } from './ConfirmDialog';
import type { Order } from '../types';
import { orderLabel } from '../utils/translations';
import { useFormat } from '../utils/format';

/**
 * `/profile?extend=<order id>` (the link in due-date reminder emails): asks to extend that
 * loan once the reader's orders are loaded. The server decides whether it is allowed.
 */
export function ExtendFromLink({
  orders,
  confirm,
  renew,
}: {
  orders: Order[];
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  renew: (order: Order) => Promise<void>;
}) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const [params, setParams] = useSearchParams();
  const orderId = params.get('extend');
  const handled = useRef<string | null>(null);

  useEffect(() => {
    if (!orderId || handled.current === orderId) return;
    const order = orders.find((item) => item.id === orderId);
    if (!order) return; // orders may still be loading
    handled.current = orderId;
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('extend');
        return next;
      },
      { replace: true },
    );
    if (order.status !== 'confirmed') {
      toast.info(t('extendLink.notBorrowed', { order: orderLabel(order) }));
      return;
    }
    void (async () => {
      const ok = await confirm({
        title: t('extendLink.title', { order: orderLabel(order) }),
        description: t('extendLink.description', { date: fmt.date(order.dueDate) }),
        confirmLabel: t('extendLink.confirm'),
      });
      if (ok) await renew(order);
    })();
  }, [orderId, orders, confirm, renew, setParams, t, fmt]);

  return null;
}
