import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShoppingCart } from 'lucide-react';
import { toast } from 'sonner';
import type { ActionResult } from '../../api/errors';
import { useCart } from '../contexts/CartContext';
import { useHolds } from '../contexts/HoldsContext';
import { errorMessage } from '../utils/apiErrors';
import { useBookText } from '../utils/bookText';
import { coverOfSize } from '../utils/covers';
import { useFormat } from '../utils/format';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

/** Profile: books held for the reader after they waited for them. */
export function HeldForYouCard() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const textOf = useBookText();
  const { holds, release } = useHolds();
  const { addBookToCart, isBookInCart } = useCart();
  const [busy, setBusy] = useState<string | null>(null);

  if (holds.length === 0) return null;

  const run = async (bookId: string, action: () => Promise<ActionResult>, done: string) => {
    setBusy(bookId);
    const result = await action();
    setBusy(null);
    if (result.ok) toast.success(done);
    else toast.error(errorMessage(t, result.error));
  };

  return (
    <Card className="border-primary/40">
      <CardHeader>
        <CardTitle>{t('holds.title')}</CardTitle>
        <CardDescription>{t('holds.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {holds.map(({ book, heldUntil }) => {
          const text = textOf(book);
          const inCart = isBookInCart(book.id);
          return (
            <div key={book.id} className="flex flex-wrap sm:flex-nowrap items-center gap-x-4 gap-y-2 p-3 border border-border rounded-lg">
              <div className="w-10 h-14 flex-shrink-0 overflow-hidden rounded bg-muted">
                <img src={coverOfSize(book.coverImage, 'S')} alt="" className="w-full h-full object-cover" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="truncate">{text.title}</h3>
                <p className="text-sm text-muted-foreground">{t('holds.until', { date: fmt.dateTime(heldUntil) })}</p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  disabled={inCart || busy === book.id}
                  onClick={() => run(book.id, () => addBookToCart(book), `${text.title}: ${t('cart.bookAdded')}`)}
                >
                  <ShoppingCart className="w-4 h-4 mr-2" aria-hidden="true" />
                  {inCart ? t('bookStatus.pending') : t('bookDetails.addToCart')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy === book.id}
                  onClick={() => run(book.id, () => release(book.id), t('holds.released', { title: text.title }))}
                >
                  {t('holds.giveUp')}
                </Button>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
