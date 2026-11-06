import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { booksApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import { useCatalog } from '../contexts/CatalogContext';
import type { Book } from '../types';
import { useBookText } from '../utils/bookText';
import { BookDetailsModal } from './BookDetailsModal';

const SHELF_SIZE = 8;

/** The newest titles, above the catalogue while nothing is searched or filtered. */
export function NewArrivalsShelf() {
  const { t } = useTranslation();
  const { version } = useCatalog();
  const textOf = useBookText();
  const [books, setBooks] = useState<Book[]>([]);
  const [selected, setSelected] = useState<Book | null>(null);

  useEffect(() => {
    let current = true;
    booksApi
      .list({ sort: '-created_at', page: 1, page_size: SHELF_SIZE })
      .then((page) => current && setBooks(page.items.map(bookFromDto)))
      .catch(() => current && setBooks([]));
    return () => {
      current = false;
    };
  }, [version]);

  if (books.length < 3) return null; // a shelf of one or two looks broken
  return (
    <section aria-labelledby="new-arrivals-title" className="mb-6">
      <h2 id="new-arrivals-title" className="flex items-center gap-2 text-lg mb-3">
        <Sparkles className="w-5 h-5 text-primary" aria-hidden="true" />
        {t('newArrivals.title')}
      </h2>
      <ul className="flex gap-4 overflow-x-auto pb-2 snap-x">
        {books.map((book) => {
          const text = textOf(book);
          return (
            <li key={book.id} className="snap-start shrink-0 w-28 sm:w-32">
              <button
                type="button"
                onClick={() => setSelected(book)}
                className="group w-full text-left rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="aspect-[3/4] overflow-hidden rounded-md bg-muted border border-border">
                  {book.coverImage && (
                    <img
                      src={book.coverImage}
                      alt=""
                      loading="lazy"
                      className="w-full h-full object-cover transition-transform group-hover:scale-105"
                    />
                  )}
                </div>
                <p className="mt-2 text-sm leading-snug line-clamp-2 group-hover:underline underline-offset-2">
                  {text.title}
                </p>
                <p className="text-xs text-muted-foreground line-clamp-1">{text.author}</p>
              </button>
            </li>
          );
        })}
      </ul>
      <BookDetailsModal book={selected} open={selected !== null} onOpenChange={(open) => !open && setSelected(null)} />
    </section>
  );
}
