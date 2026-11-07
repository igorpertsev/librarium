import { useEffect, useState } from 'react';
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
}: {
  id: string;
  title: string;
  icon: LucideIcon;
  /** Must be stable (module-level or memoised): it is reloaded when it changes. */
  load: () => Promise<Book[]>;
  /** Fewer books than this and the shelf is not shown (a shelf of one looks broken). */
  minimum?: number;
}) {
  const { version } = useCatalog();
  const textOf = useBookText();
  const [books, setBooks] = useState<Book[]>([]);
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

  if (books.length < minimum) return null;
  return (
    <section aria-labelledby={id} className="mb-6">
      <h2 id={id} className="flex items-center gap-2 text-lg mb-3">
        <Icon className="w-5 h-5 text-primary" aria-hidden="true" />
        {title}
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
                      src={coverOfSize(book.coverImage, 'M')}
                      alt=""
                      loading="lazy"
                      decoding="async"
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
