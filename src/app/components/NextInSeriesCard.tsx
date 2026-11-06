import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { usersApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import { useCatalog } from '../contexts/CatalogContext';
import type { Book } from '../types';
import { useSeriesLabel } from '../utils/catalogLists';
import { BookListRow } from './BookListRow';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

/** Profile: the next volume of each series the reader has been reading. */
export function NextInSeriesCard() {
  const { t } = useTranslation();
  const { version } = useCatalog();
  const seriesLabel = useSeriesLabel();
  const [books, setBooks] = useState<Book[]>([]);

  useEffect(() => {
    let current = true;
    usersApi
      .nextInSeries()
      .then((dtos) => current && setBooks(dtos.map(bookFromDto)))
      .catch(() => current && setBooks([]));
    return () => {
      current = false;
    };
  }, [version]);

  if (books.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('seriesNav.continueTitle')}</CardTitle>
        <CardDescription>{t('seriesNav.continueDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {books.map((book) => (
          <BookListRow key={book.id} book={book} detail={seriesLabel(book)} />
        ))}
      </CardContent>
    </Card>
  );
}
