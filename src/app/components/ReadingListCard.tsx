import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShoppingCart, X } from 'lucide-react';
import { toast } from 'sonner';
import { useCart } from '../contexts/CartContext';
import { useReadingList } from '../contexts/ReadingListContext';
import { errorMessage } from '../utils/apiErrors';
import { useBookText } from '../utils/bookText';
import { useFormat } from '../utils/format';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { WaitlistButton } from './WaitlistButton';

/** Profile: the titles a reader keeps for later, with "add to cart" when one can be borrowed. */
export function ReadingListCard() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const textOf = useBookText();
  const { items, remove } = useReadingList();
  const { addBookToCart, isBookInCart } = useCart();
  const [busy, setBusy] = useState<string | null>(null);

  if (items.length === 0) return null;

  const toCart = async (bookId: string, title: string) => {
    const item = items.find((entry) => entry.book.id === bookId);
    if (!item) return;
    setBusy(bookId);
    const result = await addBookToCart(item.book);
    setBusy(null);
    if (result.ok) toast.success(`${title}: ${t('cart.bookAdded')}`);
    else toast.error(errorMessage(t, result.error));
  };

  const drop = async (bookId: string, title: string) => {
    const result = await remove(bookId);
    if (result.ok) toast.success(t('readingList.removed', { title }));
    else toast.error(errorMessage(t, result.error));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('readingList.title')}</CardTitle>
        <CardDescription>{t('readingList.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map(({ book, addedAt }) => {
          const text = textOf(book);
          const inCart = isBookInCart(book.id);
          return (
            <div key={book.id} className="flex items-center gap-4 p-3 border border-border rounded-lg">
              <div className="w-10 h-14 flex-shrink-0 overflow-hidden rounded bg-muted">
                <img src={book.coverImage} alt="" className="w-full h-full object-cover" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="truncate">{text.title}</h3>
                <p className="text-sm text-muted-foreground truncate">
                  {text.author} · {t('readingList.since', { date: fmt.date(addedAt) })}
                </p>
              </div>
              {book.isAvailable ? (
                <Button
                  size="sm"
                  onClick={() => toCart(book.id, text.title)}
                  disabled={inCart || busy === book.id}
                >
                  <ShoppingCart className="w-4 h-4 mr-2" aria-hidden="true" />
                  {inCart ? t('bookStatus.pending') : t('bookDetails.addToCart')}
                </Button>
              ) : (
                <WaitlistButton bookId={book.id} groupId={book.groupId} title={text.title} />
              )}
              <Button
                size="icon"
                variant="ghost"
                onClick={() => drop(book.id, text.title)}
                aria-label={t('readingList.remove', { title: text.title })}
                title={t('readingList.remove', { title: text.title })}
              >
                <X className="w-4 h-4" aria-hidden="true" />
              </Button>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
