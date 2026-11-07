import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Award } from 'lucide-react';
import { libraryApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import type { BookPickDto } from '../../api/types';
import { useCatalog } from '../contexts/CatalogContext';
import type { Book } from '../types';
import { useBookText } from '../utils/bookText';
import { useNoteText } from '../utils/collections';
import { coverOfSize } from '../utils/covers';
import { useLibraryRules } from '../utils/useLibraryRules';
import { BookDetailsModal } from './BookDetailsModal';
import { Button } from './ui/button';

/** The librarians' book of the month above the catalogue. While it loads it keeps its (fixed)
 * height when the library rules say there is one, so the catalogue does not jump. */
export function BookOfTheMonth() {
  const { t } = useTranslation();
  const rules = useLibraryRules();
  const { version } = useCatalog();
  const textOf = useBookText();
  const noteOf = useNoteText();
  const [pick, setPick] = useState<{ dto: BookPickDto; book: Book } | null | undefined>(undefined);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let current = true;
    libraryApi
      .pick()
      .then((dto) => current && setPick(dto ? { dto, book: bookFromDto(dto.book) } : null))
      .catch(() => current && setPick(null));
    return () => {
      current = false;
    };
  }, [version]);

  if (pick === undefined) {
    return rules?.hasPick ? <div className="h-44 mb-6 rounded-lg bg-muted animate-pulse" aria-hidden="true" /> : null;
  }
  if (pick === null) return null;
  const text = textOf(pick.book);
  const note = noteOf(pick.dto);
  return (
    <section aria-labelledby="book-of-the-month" className="h-44 mb-6 flex gap-4 rounded-lg border border-border bg-card p-4 overflow-hidden">
      <div className="h-full aspect-[3/4] shrink-0 overflow-hidden rounded-md bg-muted">
        {pick.book.coverImage && (
          <img src={coverOfSize(pick.book.coverImage, 'M')} alt="" className="w-full h-full object-cover" fetchPriority="high" />
        )}
      </div>
      <div className="min-w-0 flex flex-col">
        <h2 id="book-of-the-month" className="flex items-center gap-2 text-sm text-primary">
          <Award className="w-4 h-4" aria-hidden="true" />
          {t('collections.bookOfTheMonth')}
        </h2>
        <p className="text-lg leading-snug line-clamp-1">{text.title}</p>
        <p className="text-sm text-muted-foreground line-clamp-1">{text.author}</p>
        {note && <p className="text-sm mt-1 line-clamp-2">{note}</p>}
        <Button size="sm" variant="outline" className="mt-auto self-start" onClick={() => setOpen(true)}>
          {t('collections.openBook')}
        </Button>
      </div>
      <BookDetailsModal book={pick.book} open={open} onOpenChange={setOpen} />
    </section>
  );
}
