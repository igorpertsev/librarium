import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CopyPlus, TriangleAlert } from 'lucide-react';
import { adminApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import type { Book } from '../types';
import { Button } from './ui/button';

const DEBOUNCE_MS = 500;

/** "This book may already be in the library" while a librarian fills in the add-book form. */
export function DuplicateWarning({
  isbn,
  title,
  author,
  onAddCopy,
}: {
  isbn: string;
  title: string;
  author: string;
  onAddCopy: (book: Book) => void;
}) {
  const { t } = useTranslation();
  const [matches, setMatches] = useState<Book[]>([]);
  const query = { isbn: isbn.trim(), title: title.trim(), author: author.trim() };
  const ready = Boolean(query.isbn || (query.title && query.author));
  const key = JSON.stringify(query);

  useEffect(() => {
    if (!ready) {
      setMatches([]);
      return;
    }
    let current = true;
    const timer = setTimeout(() => {
      const params = JSON.parse(key) as typeof query;
      adminApi
        .findDuplicates({
          isbn: params.isbn || undefined,
          title: params.title || undefined,
          author: params.author || undefined,
        })
        .then((found) => current && setMatches(found.map(bookFromDto)))
        .catch(() => current && setMatches([]));
    }, DEBOUNCE_MS);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [key, ready]);

  if (matches.length === 0) return null;
  return (
    <div role="status" className="rounded-lg border border-amber-600/50 bg-amber-500/10 p-3 space-y-2">
      <p className="flex items-center gap-2 text-sm font-medium">
        <TriangleAlert className="w-4 h-4 text-amber-700 dark:text-amber-400" aria-hidden="true" />
        {t('duplicates.title')}
      </p>
      <ul className="space-y-2">
        {matches.map((book) => (
          <li key={book.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span>
              «{book.title}» — {book.author}
              {book.isbn && <span className="text-muted-foreground"> · ISBN {book.isbn}</span>}
              <span className="text-muted-foreground"> · {t('copies.inLibrary', { count: book.copies ?? 1 })}</span>
            </span>
            <Button type="button" size="sm" variant="outline" onClick={() => onAddCopy(book)}>
              <CopyPlus className="w-4 h-4 mr-1" aria-hidden="true" />
              {t('duplicates.addCopy')}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
