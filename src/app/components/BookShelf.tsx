import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import type { LucideIcon } from 'lucide-react';
import { useCatalog } from '../contexts/CatalogContext';
import type { Book } from '../types';
import { useBookText } from '../utils/bookText';
import { coverOfSize } from '../utils/covers';
import { BookDetailsModal } from './BookDetailsModal';

/** A row of covers above the catalogue (new arrivals, suggestions); each opens the book. */
export function BookShelf({
  id,
  title,
  icon: Icon,
  load,
  minimum = 3,
  reserve = false,
  href,
}: {
  id: string;
  title: string;
  icon: LucideIcon;
  /** Must be stable (module-level or memoised): it is reloaded when it changes. */
  load: () => Promise<Book[]>;
  /** Fewer books than this and the shelf is not shown (a shelf of one looks broken). */
  minimum?: number;
  /** Keep the shelf's place while it loads, so the catalogue below does not jump (for a shelf
   * that is nearly always there). */
  reserve?: boolean;
  /** A page with the whole list (a collection): the shelf links to it. */
  href?: string;
}) {
  const { t } = useTranslation();
  const { version } = useCatalog();
  const textOf = useBookText();
  const [books, setBooks] = useState<Book[] | null>(null); // null: loading
  const [selected, setSelected] = useState<Book | null>(null);

  useEffect(() => {
    let current = true;
    load()
      .then((found) => current && setBooks(found))
      .catch(() => current && setBooks([]));
    return () => {
      current = false;
    };
  }, [load, version]);

  if (books === null) {
    if (!reserve) return null;
    return (
      <section aria-labelledby={id} aria-busy="true" className="mb-6">
        <div className="flex items-baseline justify-between gap-2 mb-3">
          <h2 id={id} className="flex items-center gap-2 text-lg">
            <Icon className="w-5 h-5 text-primary" aria-hidden="true" />
            {title}
          </h2>
          {href && (
            <Link to={href} className="text-sm text-primary underline-offset-2 hover:underline shrink-0">
              {t('collections.seeAll')}
            </Link>
          )}
        </div>
        <ul className="flex gap-4 overflow-hidden pb-2" aria-hidden="true">
          {Array.from({ length: 8 }, (_, i) => (
            <li key={i} className="shrink-0 w-28 sm:w-32">
              <div className="aspect-[3/4] rounded-md bg-muted border border-border animate-pulse" />
              <p className="mt-2 text-sm leading-snug min-h-[2lh]" />
              <p className="text-xs min-h-[1lh]" />
            </li>
          ))}
        </ul>
      </section>
    );
  }
  if (books.length < minimum) return null;
  return (
    <section aria-labelledby={id} className="mb-6">
      <div className="flex items-baseline justify-between gap-2 mb-3">
        <h2 id={id} className="flex items-center gap-2 text-lg">
          <Icon className="w-5 h-5 text-primary" aria-hidden="true" />
          {title}
        </h2>
        {href && (
          <Link to={href} className="text-sm text-primary underline-offset-2 hover:underline shrink-0">
            {t('collections.seeAll')}
          </Link>
        )}
      </div>
      <ul className="flex gap-4 overflow-x-auto pb-2 snap-x">
        {books.map((book, index) => {
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
                      src={coverOfSize(book.coverImage, 'M')}
                      alt=""
                      loading={index < 6 ? 'eager' : 'lazy'}
                      decoding="async"
                      className="w-full h-full object-cover transition-transform group-hover:scale-105"
                    />
                  )}
                </div>
                <p className="mt-2 text-sm leading-snug line-clamp-2 min-h-[2lh] group-hover:underline underline-offset-2">
                  {text.title}
                </p>
                <p className="text-xs text-muted-foreground line-clamp-1 min-h-[1lh]">{text.author}</p>
              </button>
            </li>
          );
        })}
      </ul>
      <BookDetailsModal book={selected} open={selected !== null} onOpenChange={(open) => !open && setSelected(null)} />
    </section>
  );
}
