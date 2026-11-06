import { useCallback, useEffect, useState } from 'react';
import { Book } from '../types';
import { Button } from './ui/button';
import { Card, CardContent, CardFooter } from './ui/card';
import { Badge } from './ui/badge';
import { useCart } from '../contexts/CartContext';
import { useOrders } from '../contexts/OrdersContext';
import { ShoppingCart, ChevronLeft, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import useEmblaCarousel from 'embla-carousel-react';
import { BookDetailsModal } from './BookDetailsModal';
import { useTranslation } from 'react-i18next';
import { getCartButtonLabel, getCategoryTranslation, getStatusTranslation } from '../utils/translations';
import { useFormat } from '../utils/format';
import { errorMessage } from '../utils/apiErrors';
import { WaitlistButton } from './WaitlistButton';
import { ReadingListButton } from './ReadingListButton';
import { SeriesLink, TagChips } from './CatalogFilters';
import { useBookLanguageName, useBookText } from '../utils/bookText';

interface BookCardProps {
  book: Book;
}

export function BookCard({ book }: BookCardProps) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const text = useBookText()(book);
  const languageName = useBookLanguageName()(book.language);
  const { addBookToCart, isBookInCart } = useCart();
  const { isBookUnavailable } = useOrders();
  const inCart = isBookInCart(book.id);
  // Client-side hint only; the server re-checks availability on add and on checkout.
  const inActiveOrder = Boolean(book.isReserved) || isBookUnavailable(book.id);
  const isPending = book.status === 'pending' || inCart;
  const isOrderedByOther = inActiveOrder && !inCart;
  const images = book.images || [book.coverImage];
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: true, dragFree: false });
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [adding, setAdding] = useState(false);

  const handleAddToCart = async () => {
    if (book.status === 'available' && !inCart && !inActiveOrder && !adding) {
      setAdding(true);
      const result = await addBookToCart(book);
      setAdding(false);
      if (result.ok) {
        toast.success(`${text.title}: ${t('cart.bookAdded')}`);
      } else {
        toast.error(errorMessage(t, result.error));
      }
    }
  };

  const scrollPrev = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (emblaApi) emblaApi.scrollPrev();
  }, [emblaApi]);

  const scrollNext = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (emblaApi) emblaApi.scrollNext();
  }, [emblaApi]);

  const onSelect = useCallback(() => {
    if (!emblaApi) return;
    setSelectedIndex(emblaApi.selectedScrollSnap());
  }, [emblaApi]);

  useEffect(() => {
    if (!emblaApi) return;
    onSelect();
    emblaApi.on('select', onSelect);
    return () => {
      emblaApi.off('select', onSelect);
    };
  }, [emblaApi, onSelect]);

  const getStatusBadge = () => {
    if (isPending) {
      return <Badge className="bg-blue-700 text-white hover:bg-blue-800">{t('bookStatus.pending')}</Badge>;
    }
    if (isOrderedByOther) {
      return <Badge variant="destructive">{t('bookStatus.notAvailable')}</Badge>;
    }
    const statusText = getStatusTranslation(t, book.status);
    switch (book.status) {
      case 'available':
        return <Badge className="bg-green-700 text-white hover:bg-green-800">{statusText}</Badge>;
      case 'available-soon':
        return <Badge className="bg-amber-700 text-white hover:bg-amber-800">{statusText}</Badge>;
      case 'not-available':
        return <Badge variant="destructive">{statusText}</Badge>;
    }
  };

  return (
    <>
      <Card className="h-full flex flex-col overflow-hidden hover:shadow-lg transition-shadow">
        <div
          className="aspect-[3/4] overflow-hidden bg-muted relative group cursor-pointer"
          onClick={() => setIsModalOpen(true)}
        >
          <div className="overflow-hidden h-full" ref={emblaRef}>
            <div className="flex h-full">
              {images.map((image, index) => (
                <div key={index} className="flex-[0_0_100%] min-w-0">
                  <img
                    src={image}
                    alt={t('bookDetails.imageAlt', { title: text.title, n: index + 1 })}
                    className="w-full h-full object-cover select-none"
                    draggable={false}
                  />
                </div>
              ))}
            </div>
          </div>
        {images.length > 1 && (
          <>
            <button
              type="button"
              onClick={scrollPrev}
              aria-label={t('a11y.previousImage')}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity z-10"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={scrollNext}
              aria-label={t('a11y.nextImage')}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity z-10"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1 z-10">
              {images.map((_, index) => (
                <button
                  key={index}
                  type="button"
                  aria-label={t('a11y.showImage', { n: index + 1 })}
                  aria-current={index === selectedIndex}
                  onClick={(e) => {
                    e.stopPropagation();
                    emblaApi?.scrollTo(index);
                  }}
                  className={`w-1.5 h-1.5 rounded-full transition-colors ${
                    index === selectedIndex ? 'bg-white' : 'bg-white/50'
                  }`}
                />
              ))}
            </div>
          </>
        )}
      </div>
      <CardContent className="flex-1 p-4">
        <div className="space-y-2">
          <h2 className="line-clamp-2 min-h-[3rem] text-lg">
            {/* Keyboard-accessible way to open the details (the cover is mouse-only). */}
            <button
              type="button"
              onClick={() => setIsModalOpen(true)}
              className="text-left rounded-sm hover:underline underline-offset-2 focus-visible:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {text.title}
            </button>
          </h2>
          {text.originalTitle && (
            <p className="text-xs text-muted-foreground line-clamp-1 -mt-1" lang={book.language ?? undefined}>
              <span className="sr-only">{t('translation.originalTitleLabel')} </span>
              {text.originalTitle}
            </p>
          )}
          <p className="text-sm text-muted-foreground">{text.author}</p>
          <SeriesLink book={book} className="text-sm max-w-full" />
          <div className="flex gap-2 flex-wrap">
            {getStatusBadge()}
            <Badge variant="outline">{getCategoryTranslation(t, book.category)}</Badge>
            <Badge variant="outline">{book.ageRange}</Badge>
            {languageName && (
              <Badge variant="outline">{t('translation.bookLanguage', { language: languageName })}</Badge>
            )}
          </div>
          <TagChips tags={book.tags} limit={3} />
          {isOrderedByOther && book.availableFrom && (
            <p className="text-xs text-muted-foreground">
              {t('availability.expectedBack', { date: fmt.date(book.availableFrom) })}
            </p>
          )}
          {(book.copies ?? 1) > 1 && (
            <p className="text-xs text-muted-foreground">
              {(book.copiesAvailable ?? 0) > 0
                ? t('copies.available', { available: book.copiesAvailable, count: book.copies })
                : t('copies.allOut', { count: book.copies })}
            </p>
          )}
        </div>
      </CardContent>
      <CardFooter className="p-4 pt-0 gap-2">
        <Button
          onClick={handleAddToCart}
          disabled={book.status !== 'available' || isPending || isOrderedByOther || adding}
          className="flex-1"
        >
          <ShoppingCart className="w-4 h-4 mr-2" />
          {getCartButtonLabel(t, { status: book.status, inCart: isPending, reserved: isOrderedByOther })}
        </Button>
        {(isOrderedByOther || book.status !== 'available') && !isPending && (
          <WaitlistButton bookId={book.id} groupId={book.groupId} title={text.title} />
        )}
        <ReadingListButton bookId={book.id} groupId={book.groupId} title={text.title} />
      </CardFooter>
    </Card>

    <BookDetailsModal
      book={book}
      open={isModalOpen}
      onOpenChange={setIsModalOpen}
    />
    </>
  );
}
