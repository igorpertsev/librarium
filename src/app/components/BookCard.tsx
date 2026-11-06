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
import { errorMessage } from '../utils/apiErrors';

interface BookCardProps {
  book: Book;
}

export function BookCard({ book }: BookCardProps) {
  const { t } = useTranslation();
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
        toast.success(`${book.title}: ${t('cart.bookAdded')}`);
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
      return <Badge className="bg-blue-700 hover:bg-blue-800">{t('bookStatus.pending')}</Badge>;
    }
    if (isOrderedByOther) {
      return <Badge variant="destructive">{t('bookStatus.notAvailable')}</Badge>;
    }
    const statusText = getStatusTranslation(t, book.status);
    switch (book.status) {
      case 'available':
        return <Badge className="bg-green-700 hover:bg-green-800">{statusText}</Badge>;
      case 'available-soon':
        return <Badge className="bg-amber-700 hover:bg-amber-800">{statusText}</Badge>;
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
                    alt={`${book.title} - Image ${index + 1}`}
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
              onClick={scrollPrev}
              className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity z-10"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={scrollNext}
              className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity z-10"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1 z-10">
              {images.map((_, index) => (
                <button
                  key={index}
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
          <h3 className="line-clamp-2 min-h-[3rem]">{book.title}</h3>
          <p className="text-sm text-muted-foreground">{book.author}</p>
          <div className="flex gap-2 flex-wrap">
            {getStatusBadge()}
            <Badge variant="outline">{getCategoryTranslation(t, book.category)}</Badge>
            <Badge variant="outline">{book.ageRange}</Badge>
          </div>
        </div>
      </CardContent>
      <CardFooter className="p-4 pt-0">
        <Button
          onClick={handleAddToCart}
          disabled={book.status !== 'available' || isPending || isOrderedByOther || adding}
          className="w-full"
        >
          <ShoppingCart className="w-4 h-4 mr-2" />
          {getCartButtonLabel(t, { status: book.status, inCart: isPending, reserved: isOrderedByOther })}
        </Button>
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
