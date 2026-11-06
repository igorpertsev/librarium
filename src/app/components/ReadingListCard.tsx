import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { toast } from 'sonner';
import { useReadingList } from '../contexts/ReadingListContext';
import { errorMessage } from '../utils/apiErrors';
import { useBookText } from '../utils/bookText';
import { useFormat } from '../utils/format';
import { BookListRow } from './BookListRow';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

/** Profile: the titles a reader keeps for later. */
export function ReadingListCard() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const textOf = useBookText();
  const { items, remove } = useReadingList();

  if (items.length === 0) return null;

  const drop = async (bookId: string, title: string) => {
    const result = await remove(bookId);
    if (result.ok) toast.success(t('readingList.removed', { title }));
    else toast.error(errorMessage(t, result.error));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('readingList.title')}</CardTitle>
        <CardDescription>{t('readingList.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map(({ book, addedAt }) => {
          const text = textOf(book);
          return (
            <BookListRow
              key={book.id}
              book={book}
              detail={`${text.author} · ${t('readingList.since', { date: fmt.date(addedAt) })}`}
              actions={
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => drop(book.id, text.title)}
                  aria-label={t('readingList.remove', { title: text.title })}
                  title={t('readingList.remove', { title: text.title })}
                >
                  <X className="w-4 h-4" aria-hidden="true" />
                </Button>
              }
            />
          );
        })}
      </CardContent>
    </Card>
  );
}
