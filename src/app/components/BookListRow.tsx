import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ShoppingCart } from 'lucide-react';
import { toast } from 'sonner';
import { useCart } from '../contexts/CartContext';
import type { Book } from '../types';
import { errorMessage } from '../utils/apiErrors';
import { useBookText } from '../utils/bookText';
import { Button } from './ui/button';
import { WaitlistButton } from './WaitlistButton';
import { coverOfSize } from '../utils/covers';

/** A book in a profile list: cover, title, a line of detail, and "add to cart" or "notify me". */
export function BookListRow({ book, detail, actions }: { book: Book; detail: ReactNode; actions?: ReactNode }) {
  const { t } = useTranslation();
  const text = useBookText()(book);
  const { addBookToCart, isBookInCart } = useCart();
  const [busy, setBusy] = useState(false);
  const inCart = isBookInCart(book.id);

  const toCart = async () => {
    setBusy(true);
    const result = await addBookToCart(book);
    setBusy(false);
    if (result.ok) toast.success(`${text.title}: ${t('cart.bookAdded')}`);
    else toast.error(errorMessage(t, result.error));
  };

  return (
    <div className="flex flex-wrap sm:flex-nowrap items-center gap-x-4 gap-y-2 p-3 border border-border rounded-lg">
      <div className="w-10 h-14 flex-shrink-0 overflow-hidden rounded bg-muted">
        <img src={coverOfSize(book.coverImage, 'S')} alt="" loading="lazy" className="w-full h-full object-cover" />
      </div>
      <div className="flex-1 min-w-0">
        <h3 className="truncate">{text.title}</h3>
        <p className="text-sm text-muted-foreground truncate">{detail}</p>
      </div>
      <div className="flex items-center gap-2">
        {book.isAvailable ? (
          <Button size="sm" onClick={toCart} disabled={inCart || busy}>
            <ShoppingCart className="w-4 h-4 mr-2" aria-hidden="true" />
            {inCart ? t('bookStatus.pending') : t('bookDetails.addToCart')}
          </Button>
        ) : (
          <WaitlistButton bookId={book.id} groupId={book.groupId} title={text.title} />
        )}
        {actions}
      </div>
    </div>
  );
}
