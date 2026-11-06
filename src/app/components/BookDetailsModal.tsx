import { useCallback, useEffect, useState } from 'react';
import { Book } from '../types';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { ChevronLeft, ChevronRight, ShoppingCart, Calendar, Hash, BookOpen, ZoomIn, ZoomOut, X, LogIn, Link2 } from 'lucide-react';
import { Separator } from './ui/separator';
import useEmblaCarousel from 'embla-carousel-react';
import { useCart } from '../contexts/CartContext';
import { useAuth } from '../contexts/AuthContext';
import { useSignInFirst } from '../utils/useSignInFirst';
import { useLibraryRules } from '../utils/useLibraryRules';
import { useOrders } from '../contexts/OrdersContext';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { getCartButtonLabel, getCategoryTranslation } from '../utils/translations';
import { useFormat } from '../utils/format';
import { errorMessage } from '../utils/apiErrors';
import { WaitlistButton } from './WaitlistButton';
import { ReadingListButton } from './ReadingListButton';
import { AuthorLink, SeriesLink, TagChips } from './CatalogFilters';
import { useBookLanguageName, useBookText } from '../utils/bookText';
import { booksApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import { coverOfSize } from '../utils/covers';
import { BookReviews } from './BookReviews';

interface BookDetailsModalProps {
  book: Book | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BookDetailsModal({ book: initialBook, open, onOpenChange }: BookDetailsModalProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const rules = useLibraryRules();
  const signInFirst = useSignInFirst();
  const copyLink = async (bookId: string) => {
    const url = `${window.location.origin}/books/${bookId}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success(t('share.copied'));
    } catch {
      toast.info(url); // no clipboard access: show the link to copy by hand
    }
  };
  // "Previous / next volume" shows another book in the same dialog.
  const [shown, setShown] = useState<Book | null>(null);
  const book = shown ?? initialBook;
  const [neighbours, setNeighbours] = useState<{ previous: Book | null; next: Book | null }>({
    previous: null,
    next: null,
  });
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
  const textOf = useBookText();
  const languageNameOf = useBookLanguageName();
  const [showOriginal, setShowOriginal] = useState(false);
  const bookId = book?.id;
  const inNumberedSeries = Boolean(book?.series) && book?.seriesPosition != null;

  useEffect(() => {
    if (!open || !bookId || !inNumberedSeries) {
      setNeighbours({ previous: null, next: null });
      return;
    }
    let current = true;
    booksApi
      .seriesNeighbours(bookId)
      .then((found) => {
        if (current) {
          setNeighbours({
            previous: found.previous ? bookFromDto(found.previous) : null,
            next: found.next ? bookFromDto(found.next) : null,
          });
        }
      })
      .catch(() => current && setNeighbours({ previous: null, next: null }));
    return () => {
      current = false;
    };
  }, [open, bookId, inNumberedSeries]);

  // "Readers who borrowed this also borrowed".
  const [alsoBorrowed, setAlsoBorrowed] = useState<Book[]>([]);
  useEffect(() => {
    if (!open || !bookId) {
      setAlsoBorrowed([]);
      return;
    }
    let current = true;
    booksApi
      .alsoBorrowed(bookId)
      .then((found) => current && setAlsoBorrowed(found.map(bookFromDto)))
      .catch(() => current && setAlsoBorrowed([]));
    return () => {
      current = false;
    };
  }, [open, bookId]);

  const showVolume = (volume: Book) => {
    setShown(volume);
    setShowOriginal(false);
    setSelectedIndex(0);
  };
  const handleOpenChange = (next: boolean) => {
    if (!next) setShown(null);
    onOpenChange(next);
  };
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
      return <Badge className="bg-blue-700 text-white hover:bg-blue-800">{t('bookStatus.pending')}</Badge>;
    }
    if (isOrderedByOther) {
      return <Badge variant="destructive">{t('bookStatus.notAvailable')}</Badge>;
    }
    switch (book.status) {
      case 'available':
        return <Badge className="bg-green-700 text-white hover:bg-green-800">{t('bookStatus.available')}</Badge>;
      case 'available-soon':
        return <Badge className="bg-amber-700 text-white hover:bg-amber-800">{t('bookStatus.availableSoon')}</Badge>;
      case 'not-available':
        return <Badge variant="destructive">{t('bookStatus.notAvailable')}</Badge>;
    }
  };

  if (!book) return null;
  const text = textOf(book);
  const languageName = languageNameOf(book.language);
  const translation = text.translation;
  const description = showOriginal ? book.description : text.description;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent key={book.id} className="sm:max-w-6xl max-h-[90vh] overflow-y-auto p-4 sm:p-8">
        <DialogHeader>
          <DialogTitle className="text-xl sm:text-3xl">{text.title}</DialogTitle>
          <DialogDescription className="text-sm sm:text-lg">{t('bookDetails.byAuthor', { author: text.author })}</DialogDescription>
          {text.originalTitle && (
            <p className="text-sm text-muted-foreground">
              {t('translation.originalTitleLabel')}{' '}
              <span lang={book.language ?? undefined}>{text.originalTitle}</span>
              {text.originalAuthor && <span lang={book.language ?? undefined}> — {text.originalAuthor}</span>}
            </p>
          )}
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
              {languageName && (
                <Badge variant="outline" className="text-xs sm:text-base px-2 sm:px-4 py-0.5 sm:py-1.5">
                  {t('translation.bookLanguage', { language: languageName })}
                </Badge>
              )}
            </div>
            {(book.series || (book.tags?.length ?? 0) > 0) && (
              <div className="space-y-2">
                <SeriesLink book={book} onNavigate={() => handleOpenChange(false)} className="text-sm sm:text-base" />
                {(neighbours.previous || neighbours.next) && (
                  <nav aria-label={t('seriesNav.label')} className="flex flex-wrap gap-2">
                    {neighbours.previous && (
                      <Button variant="outline" size="sm" onClick={() => showVolume(neighbours.previous!)}>
                        <ChevronLeft className="w-4 h-4 mr-1" aria-hidden="true" />
                        {t('seriesNav.previous', { title: textOf(neighbours.previous).title })}
                      </Button>
                    )}
                    {neighbours.next && (
                      <Button variant="outline" size="sm" onClick={() => showVolume(neighbours.next!)}>
                        {t('seriesNav.next', { title: textOf(neighbours.next).title })}
                        <ChevronRight className="w-4 h-4 ml-1" aria-hidden="true" />
                      </Button>
                    )}
                  </nav>
                )}
                <TagChips tags={book.tags} onNavigate={() => handleOpenChange(false)} />
              </div>
            )}
            {isOrderedByOther && book.availableFrom && (
              <p className="text-sm text-muted-foreground">
                {t('availability.expectedBack', { date: fmt.date(book.availableFrom) })}
              </p>
            )}
            {(book.copies ?? 1) > 1 && (
              <p className="text-sm text-muted-foreground">
                {(book.copiesAvailable ?? 0) > 0
                  ? t('copies.available', { available: book.copiesAvailable, count: book.copies })
                  : t('copies.allOut', { count: book.copies })}
              </p>
            )}

            <Separator />

            <div>
              <h3 className="mb-2 sm:mb-4 text-base sm:text-xl">{t('bookDetails.description')}</h3>
              <p
                className="text-muted-foreground leading-relaxed text-sm sm:text-base"
                lang={showOriginal || !text.descriptionTranslated ? book.language ?? undefined : translation?.language}
              >
                {description}
              </p>
              {text.descriptionTranslated && translation && (
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  {!showOriginal && translation.descriptionSource === 'wikipedia' && translation.sourceUrl && (
                    <span>
                      {t('translation.source')}{' '}
                      <a
                        href={translation.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline underline-offset-2 hover:text-foreground"
                      >
                        {t('translation.wikipedia')}
                      </a>{' '}
                      (CC BY-SA)
                    </span>
                  )}
                  {!showOriginal && translation.descriptionSource === 'machine' && (
                    <span>{t('translation.machineDescription')}</span>
                  )}
                  {book.description && (
                    <button
                      type="button"
                      onClick={() => setShowOriginal((value) => !value)}
                      className="underline underline-offset-2 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                    >
                      {showOriginal ? t('translation.showTranslation') : t('translation.showOriginal')}
                    </button>
                  )}
                </div>
              )}
              {translation?.titleSource === 'machine' && (
                <p className="mt-1 text-xs text-muted-foreground">{t('translation.machineTitle')}</p>
              )}
            </div>

            <BookReviews bookId={book.id} />

            {alsoBorrowed.length > 0 && (
              <section aria-labelledby="also-borrowed-title">
                <h3 id="also-borrowed-title" className="mb-2 text-base sm:text-xl">{t('alsoBorrowed.title')}</h3>
                <ul className="flex gap-3 overflow-x-auto pb-1">
                  {alsoBorrowed.map((other) => (
                    <li key={other.id} className="shrink-0 w-20">
                      <button
                        type="button"
                        onClick={() => showVolume(other)}
                        className="w-full text-left rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <div className="aspect-[3/4] overflow-hidden rounded bg-muted border border-border">
                          {other.coverImage && (
                            <img src={coverOfSize(other.coverImage, 'S')} alt="" loading="lazy" className="w-full h-full object-cover" />
                          )}
                        </div>
                        <span className="mt-1 block text-xs leading-snug line-clamp-2">{textOf(other).title}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <Separator />

            <div className="space-y-3 sm:space-y-5">
              <div className="flex items-center gap-3 sm:gap-4">
                <BookOpen className="w-4 h-4 sm:w-6 sm:h-6 text-muted-foreground" />
                <div>
                  <p className="text-xs sm:text-sm text-muted-foreground mb-0.5 sm:mb-1">{t('bookDetails.author')}</p>
                  <p className="text-sm sm:text-lg">
                    <AuthorLink author={book.author} label={text.author} onNavigate={() => handleOpenChange(false)} />
                  </p>
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

            {user ? (
              <>
                <Button
                  onClick={handleAddToCart}
                  disabled={book.status !== 'available' || isPending || isOrderedByOther || adding}
                  className="w-full text-sm sm:text-lg py-5 sm:py-7"
                  size="lg"
                >
                  <ShoppingCart className="w-4 h-4 sm:w-6 sm:h-6 mr-2 sm:mr-3" />
                  {getCartButtonLabel(t, { status: book.status, inCart: isPending, reserved: isOrderedByOther })}
                </Button>
                {(isOrderedByOther || book.status !== 'available') && !isPending && (
                  <div className="flex flex-col items-center gap-2 text-center">
                    <p className="text-sm text-muted-foreground">{t('waitlist.explain')}</p>
                    {rules && rules.holdHours > 0 && (
                      <p className="text-xs text-muted-foreground">{t('waitlist.holdExplain', { count: rules.holdHours })}</p>
                    )}
                    <WaitlistButton bookId={book.id} groupId={book.groupId} title={text.title} withLabel />
                  </div>
                )}
                <div className="flex justify-center">
                  <ReadingListButton bookId={book.id} groupId={book.groupId} title={text.title} withLabel />
                </div>
              </>
            ) : (
              <div className="space-y-2 text-center">
                <Button onClick={signInFirst} className="w-full text-sm sm:text-lg py-5 sm:py-7" size="lg">
                  <LogIn className="w-4 h-4 sm:w-6 sm:h-6 mr-2 sm:mr-3" aria-hidden="true" />
                  {t('guest.signInToBorrow')}
                </Button>
                <p className="text-sm text-muted-foreground">{t('guest.explain')}</p>
              </div>
            )}
            <div className="flex justify-center">
              <Button variant="ghost" size="sm" onClick={() => void copyLink(book.id)}>
                <Link2 className="w-4 h-4 mr-2" aria-hidden="true" />
                {t('share.copyLink')}
              </Button>
            </div>
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
                  alt={t('bookDetails.zoomedAlt', { title: text.title, n: selectedIndex + 1 })}
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
