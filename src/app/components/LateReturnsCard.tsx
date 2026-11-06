import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import type { Order } from '../types';
import { daysUntil, useFormat } from '../utils/format';
import { useLibraryRules } from '../utils/useLibraryRules';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';

/** Fee owed so far for an overdue loan (the library's fee per day × days late). */
function accruedLateFee(order: Pick<Order, 'dueDate'>, feePerDay: number): number {
  const daysLate = -daysUntil(order.dueDate);
  return daysLate > 0 ? Math.round(daysLate * feePerDay * 100) / 100 : 0;
}

/** Profile: overdue loans (orders paused, fee so far) and late fees still owed. */
export function LateReturnsCard({ orders }: { orders: Order[] }) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const rules = useLibraryRules();

  const overdue = orders.filter((o) => o.status === 'confirmed' && daysUntil(o.dueDate) < 0);
  const unpaid = orders.filter((o) => o.status === 'returned' && (o.lateFee ?? 0) > 0 && !o.lateFeeSettledAt);
  if (overdue.length === 0 && unpaid.length === 0) return null;

  const currency = rules?.currency ?? overdue[0]?.currency ?? unpaid[0]?.currency;
  const feePerDay = rules?.lateFeePerDay ?? 0;
  const accrued = overdue.reduce((sum, o) => sum + accruedLateFee(o, feePerDay), 0);
  const owed = unpaid.reduce((sum, o) => sum + (o.lateFee ?? 0), 0);
  const numbers = (list: Order[]) => list.map((o) => (o.number ? `#${o.number}` : '')).filter(Boolean).join(', ');

  return (
    <Alert variant="destructive" data-testid="late-returns">
      <AlertTriangle className="h-4 w-4" aria-hidden="true" />
      <AlertTitle>{overdue.length > 0 ? t('late.overdueTitle', { count: overdue.length }) : t('late.owedTitle')}</AlertTitle>
      <AlertDescription className="space-y-1">
        {overdue.length > 0 && (
          <>
            <p>{t('late.overdueText', { orders: numbers(overdue) })}</p>
            {rules?.blockOverdue && <p>{t('late.ordersPaused')}</p>}
            {accrued > 0 && <p>{t('late.accrued', { amount: fmt.money(accrued, currency), perDay: fmt.money(feePerDay, currency) })}</p>}
          </>
        )}
        {unpaid.length > 0 && (
          <p>{t('late.owed', { amount: fmt.money(owed, currency), orders: numbers(unpaid) })}</p>
        )}
      </AlertDescription>
    </Alert>
  );
}
