import { useCallback, useEffect, useState } from 'react';
import { Book } from '../types';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { ChevronLeft, ChevronRight, ShoppingCart, Calendar, Hash, BookOpen, ZoomIn, ZoomOut, X } from 'lucide-react';
import { Separator } from './ui/separator';
import useEmblaCarousel from 'embla-carousel-react';
import { useCart } from '../contexts/CartContext';
import { useOrders } from '../contexts/OrdersContext';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { getCartButtonLabel, getCategoryTranslation } from '../utils/translations';
import { useFormat } from '../utils/format';
import { errorMessage } from '../utils/apiErrors';

interface BookDetailsModalProps {
  book: Book | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BookDetailsModal({ book, open, onOpenChange }: BookDetailsModalProps) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const { addBookToCart, isBookInCart } = useCart();
  const { isBookUnavailable } = useOrders();
  const inCart = book ? isBookInCart(book.id) : false;
  const inActiveOrder = book ? Boolean(book.isReserved) || isBookUnavailable(book.id) : false;
  const isPending = book?.status === 'pending' || inCart;
  const isOrderedByOther = inActiveOrder && !inCart;
  const images = book?.images || (book ? [book.coverImage] : []);
  const [emblaRef, emblaApi] = useEmblaCarousel({ loop: true, dragFree: false });
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isZoomed, setIsZoomed] = useState(false);
  const [zoomScale, setZoomScale] = useState(1);

  const scrollPrev = useCallback(() => {
    if (emblaApi) emblaApi.scrollPrev();
  }, [emblaApi]);

  const scrollNext = useCallback(() => {
    if (emblaApi) emblaApi.scrollNext();
  }, [emblaApi]);

  const onSelect = useCallback(() => {
    if (!emblaApi) return;
    setSelectedIndex(emblaApi.selectedScrollSnap());
  }, [emblaApi]);

  const handleImageClick = () => {
    setIsZoomed(true);
    setZoomScale(1);
  };

  const handleZoomIn = () => {
    setZoomScale(prev => Math.min(prev + 0.5, 3));
  };

  const handleZoomOut = () => {
    setZoomScale(prev => Math.max(prev - 0.5, 1));
  };

  const handleCloseZoom = () => {
    setIsZoomed(false);
    setZoomScale(1);
  };

  useEffect(() => {
    if (!emblaApi) return;
    onSelect();
    emblaApi.on('select', onSelect);
    return () => {
      emblaApi.off('select', onSelect);
    };
  }, [emblaApi, onSelect]);

  const [adding, setAdding] = useState(false);

  const handleAddToCart = async () => {
    if (book && book.status === 'available' && !inCart && !inActiveOrder && !adding) {
      setAdding(true);
      const result = await addBookToCart(book);
      setAdding(false);
      if (result.ok) {
        toast.success(t('cart.bookAdded'));
      } else {
        toast.error(errorMessage(t, result.error));
      }
    }
  };

  const getStatusBadge = () => {
    if (!book) return null;
    if (isPending) {
      return <Badge className="bg-blue-700 hover:bg-blue-800">{t('bookStatus.pending')}</Badge>;
    }
    if (isOrderedByOther) {
      return <Badge variant="destructive">{t('bookStatus.notAvailable')}</Badge>;
    }
    switch (book.status) {
      case 'available':
        return <Badge className="bg-green-700 hover:bg-green-800">{t('bookStatus.available')}</Badge>;
      case 'available-soon':
        return <Badge className="bg-amber-700 hover:bg-amber-800">{t('bookStatus.availableSoon')}</Badge>;
      case 'not-available':
        return <Badge variant="destructive">{t('bookStatus.notAvailable')}</Badge>;
    }
  };

  if (!book) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-6xl max-h-[90vh] overflow-y-auto p-4 sm:p-8">
        <DialogHeader>
          <DialogTitle className="text-xl sm:text-3xl">{book.title}</DialogTitle>
          <DialogDescription className="text-sm sm:text-lg">{t('bookDetails.byAuthor', { author: book.author })}</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-8">
          <div className="space-y-3 sm:space-y-5">
            <div
              className="aspect-[3/4] h-[400px] sm:h-[550px] overflow-hidden bg-muted relative group rounded-lg sm:rounded-xl shadow-xl sm:shadow-2xl cursor-zoom-in"
              onClick={handleImageClick}
            >
              <div className="overflow-hidden h-full" ref={emblaRef}>
                <div className="flex h-full">
                  {images.map((image, index) => (
                    <div key={index} className="flex-[0_0_100%] min-w-0">
                      <img
                        src={image}
                        alt={t('bookDetails.imageAlt', { title: book.title, n: index + 1 })}
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
                    className="absolute left-2 sm:left-4 top-1/2 -translate-y-1/2 bg-black/70 hover:bg-black/90 text-white p-2 sm:p-3 rounded-full opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity z-10 shadow-lg"
                  >
                    <ChevronLeft className="w-5 h-5 sm:w-7 sm:h-7" />
                  </button>
                  <button
                    type="button"
                    onClick={scrollNext}
                    aria-label={t('a11y.nextImage')}
                    className="absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 bg-black/70 hover:bg-black/90 text-white p-2 sm:p-3 rounded-full opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity z-10 shadow-lg"
                  >
                    <ChevronRight className="w-5 h-5 sm:w-7 sm:h-7" />
                  </button>
                  <div className="absolute bottom-3 sm:bottom-6 left-1/2 -translate-x-1/2 flex gap-1.5 sm:gap-2.5 z-10">
                    {images.map((_, index) => (
                      <button
                        key={index}
                        type="button"
                        aria-label={t('a11y.showImage', { n: index + 1 })}
                        aria-current={index === selectedIndex}
                        onClick={() => emblaApi?.scrollTo(index)}
                        className={`w-2 h-2 sm:w-3 sm:h-3 rounded-full transition-all shadow-md ${
                          index === selectedIndex ? 'bg-white scale-125' : 'bg-white/60 hover:bg-white/80'
                        }`}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>

            {images.length > 1 && (
              <div className="grid grid-cols-4 sm:grid-cols-5 gap-2 sm:gap-3">
                {images.map((image, index) => (
                  <button
                    key={index}
                    onClick={() => emblaApi?.scrollTo(index)}
                    className={`aspect-[3/4] rounded sm:rounded-lg overflow-hidden border-2 transition-all hover:scale-105 shadow-sm sm:shadow-md ${
                      index === selectedIndex ? 'border-primary ring-2 ring-primary/50 scale-105' : 'border-border hover:border-primary/50'
                    }`}
                  >
                    <img
                      src={image}
                      alt={t('bookDetails.thumbnailAlt', { n: index + 1 })}
                      className="w-full h-full object-cover"
                    />
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-4 sm:space-y-6">
            <div className="flex gap-2 sm:gap-3 flex-wrap">
              {getStatusBadge()}
              <Badge variant="outline" className="text-xs sm:text-base px-2 sm:px-4 py-0.5 sm:py-1.5">{getCategoryTranslation(t, book.category)}</Badge>
              <Badge variant="outline" className="text-xs sm:text-base px-2 sm:px-4 py-0.5 sm:py-1.5">{book.ageRange}</Badge>
            </div>
            {isOrderedByOther && book.availableFrom && (
              <p className="text-sm text-muted-foreground">
                {t('availability.expectedBack', { date: fmt.date(book.availableFrom) })}
              </p>
            )}

            <Separator />

            <div>
              <h3 className="mb-2 sm:mb-4 text-base sm:text-xl">{t('bookDetails.description')}</h3>
              <p className="text-muted-foreground leading-relaxed text-sm sm:text-base">{book.description}</p>
            </div>

            <Separator />

            <div className="space-y-3 sm:space-y-5">
              <div className="flex items-center gap-3 sm:gap-4">
                <BookOpen className="w-4 h-4 sm:w-6 sm:h-6 text-muted-foreground" />
                <div>
                  <p className="text-xs sm:text-sm text-muted-foreground mb-0.5 sm:mb-1">{t('bookDetails.author')}</p>
                  <p className="text-sm sm:text-lg">{book.author}</p>
                </div>
              </div>

              <div className="flex items-center gap-3 sm:gap-4">
                <Hash className="w-4 h-4 sm:w-6 sm:h-6 text-muted-foreground" />
                <div>
                  <p className="text-xs sm:text-sm text-muted-foreground mb-0.5 sm:mb-1">{t('bookDetails.isbn')}</p>
                  <p className="text-sm sm:text-lg font-mono">{book.isbn}</p>
                </div>
              </div>

              <div className="flex items-center gap-3 sm:gap-4">
                <Calendar className="w-4 h-4 sm:w-6 sm:h-6 text-muted-foreground" />
                <div>
                  <p className="text-xs sm:text-sm text-muted-foreground mb-0.5 sm:mb-1">{t('bookDetails.publishedYear')}</p>
                  <p className="text-sm sm:text-lg">{book.publishedYear}</p>
                </div>
              </div>
            </div>

            <Separator />

            <Button
              onClick={handleAddToCart}
              disabled={book.status !== 'available' || isPending || isOrderedByOther || adding}
              className="w-full text-sm sm:text-lg py-5 sm:py-7"
              size="lg"
            >
              <ShoppingCart className="w-4 h-4 sm:w-6 sm:h-6 mr-2 sm:mr-3" />
              {getCartButtonLabel(t, { status: book.status, inCart: isPending, reserved: isOrderedByOther })}
            </Button>
          </div>
        </div>

        {isZoomed && (
          <div
            className="fixed inset-0 z-[100] bg-black/95 flex items-center justify-center"
            onClick={handleCloseZoom}
          >
            <div className="relative w-full h-full flex items-center justify-center p-4">
              <div
                className="relative max-w-full max-h-full overflow-auto"
                onClick={(e) => e.stopPropagation()}
              >
                <img
                  src={images[selectedIndex]}
                  alt={t('bookDetails.zoomedAlt', { title: book.title, n: selectedIndex + 1 })}
                  className="max-w-none transition-transform duration-200 cursor-zoom-in"
                  style={{ transform: `scale(${zoomScale})` }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (zoomScale < 3) {
                      handleZoomIn();
                    }
                  }}
                />
              </div>

              <div className="absolute top-4 right-4 flex gap-2">
                <button
                  type="button"
                  aria-label={t('a11y.zoomOut')}
                  onClick={(e) => { e.stopPropagation(); handleZoomOut(); }}
                  disabled={zoomScale <= 1}
                  className="bg-black/60 hover:bg-black/80 text-white p-3 rounded-full disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                >
                  <ZoomOut className="w-6 h-6" />
                </button>
                <button
                  type="button"
                  aria-label={t('a11y.zoomIn')}
                  onClick={(e) => { e.stopPropagation(); handleZoomIn(); }}
                  disabled={zoomScale >= 3}
                  className="bg-black/60 hover:bg-black/80 text-white p-3 rounded-full disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                >
                  <ZoomIn className="w-6 h-6" />
                </button>
                <button
                  type="button"
                  aria-label={t('a11y.closeZoom')}
                  onClick={handleCloseZoom}
                  className="bg-black/60 hover:bg-black/80 text-white p-3 rounded-full transition-opacity"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>

              {images.length > 1 && (
                <>
                  <button
                    type="button"
                    aria-label={t('a11y.previousImage')}
                    onClick={(e) => { e.stopPropagation(); scrollPrev(); }}
                    className="absolute left-4 top-1/2 -translate-y-1/2 bg-black/60 hover:bg-black/80 text-white p-4 rounded-full transition-opacity"
                  >
                    <ChevronLeft className="w-8 h-8" />
                  </button>
                  <button
                    type="button"
                    aria-label={t('a11y.nextImage')}
                    onClick={(e) => { e.stopPropagation(); scrollNext(); }}
                    className="absolute right-4 top-1/2 -translate-y-1/2 bg-black/60 hover:bg-black/80 text-white p-4 rounded-full transition-opacity"
                  >
                    <ChevronRight className="w-8 h-8" />
                  </button>
                  <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex gap-3">
                    {images.map((_, index) => (
                      <button
                        key={index}
                        type="button"
                        aria-label={t('a11y.showImage', { n: index + 1 })}
                        onClick={(e) => { e.stopPropagation(); emblaApi?.scrollTo(index); }}
                        className={`w-3 h-3 rounded-full transition-all ${
                          index === selectedIndex ? 'bg-white scale-125' : 'bg-white/60 hover:bg-white/80'
                        }`}
                      />
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
