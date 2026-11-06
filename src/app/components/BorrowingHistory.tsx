import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, RotateCcw, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useCart } from '../contexts/CartContext';
import type { Order } from '../types';
import { useFormat } from '../utils/format';
import { orderLabel } from '../utils/translations';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

const INITIAL_COUNT = 5;

/** Past orders (returned or cancelled), newest first, with "Borrow again". */
export function BorrowingHistory({ orders }: { orders: Order[] }) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const navigate = useNavigate();
  const { addBookToCart, isBookInCart } = useCart();
  const [showAll, setShowAll] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const past = orders
    .filter((o) => o.status === 'returned' || o.status === 'cancelled')
    .sort((a, b) => (b.returnedAt ?? b.cancelledAt ?? b.orderedAt).localeCompare(a.returnedAt ?? a.cancelledAt ?? a.orderedAt));
  if (past.length === 0) return null;
  const visible = showAll ? past : past.slice(0, INITIAL_COUNT);

  // Adds every book of the order that can be borrowed now; the server checks each one.
  const borrowAgain = async (order: Order) => {
    setBusyId(order.id);
    let added = 0;
    let unavailable = 0;
    for (const book of order.books) {
      if (isBookInCart(book.id)) continue;
      const result = await addBookToCart(book);
      if (result.ok) added += 1;
      else unavailable += 1;
    }
    setBusyId(null);
    const goToCart = { label: t('history.goToCart'), onClick: () => navigate('/cart') };
    if (added > 0 && unavailable === 0) toast.success(t('history.added', { count: added }), { action: goToCart });
    else if (added > 0) toast.warning(t('history.addedSome', { count: added, unavailable }), { action: goToCart });
    else if (unavailable > 0) toast.error(t('history.noneAvailable'));
    else toast.info(t('history.alreadyInCart'));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('history.title')}</CardTitle>
        <CardDescription>{t('history.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {visible.map((order) => {
          const returned = order.status === 'returned';
          return (
            <section key={order.id} aria-label={orderLabel(order)} className="p-4 border border-border rounded-lg bg-muted/30 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">{orderLabel(order)}</span>
                  {returned ? (
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <CheckCircle2 className="w-4 h-4 text-green-700" aria-hidden="true" />
                      {t('profile.returnedOn')}: {fmt.date(order.returnedAt)}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <XCircle className="w-4 h-4" aria-hidden="true" />
                      {t('history.cancelledOn')}: {fmt.date(order.cancelledAt ?? order.orderedAt)}
                    </span>
                  )}
                  <Badge variant="outline">{order.books.length} {t('cart.books')}</Badge>
                </div>
                <Button variant="outline" size="sm" disabled={busyId === order.id} onClick={() => borrowAgain(order)}>
                  <RotateCcw className="w-4 h-4 mr-2" aria-hidden="true" />
                  {t('history.borrowAgain')}
                </Button>
              </div>
              <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                {order.books.map((book) => (
                  <li key={book.id}>
                    <span className="text-foreground">{book.title}</span> — {book.author}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
        {past.length > INITIAL_COUNT && (
          <Button variant="ghost" size="sm" onClick={() => setShowAll((value) => !value)} aria-expanded={showAll}>
            {showAll ? t('history.showLess') : t('history.showAll', { count: past.length })}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
