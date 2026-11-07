import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { Library } from 'lucide-react';
import { collectionsApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import type { CollectionDto } from '../../api/types';
import { BookCard } from '../components/BookCard';
import type { Book } from '../types';
import { useCollectionText } from '../utils/collections';

/** A collection's page: its description and every title in the librarians' order. */
export default function CollectionPage() {
  const { t } = useTranslation();
  const { slug = '' } = useParams();
  const textOf = useCollectionText();
  const [state, setState] = useState<{ collection: CollectionDto; books: Book[] } | null | undefined>(undefined);

  useEffect(() => {
    let current = true;
    collectionsApi
      .get(slug)
      .then((collection) => current && setState({ collection, books: collection.books.map(bookFromDto) }))
      .catch(() => current && setState(null));
    return () => {
      current = false;
    };
  }, [slug]);

  const text = state ? textOf(state.collection) : null;
  useEffect(() => {
    document.title = `${text?.title ?? t('collections.title')} — Little Dragon`;
  }, [text?.title, t]);

  if (state === undefined) {
    return <p className="container mx-auto px-4 py-8 text-muted-foreground">{t('common.loading')}</p>;
  }
  if (state === null || !text) {
    return (
      <div className="container mx-auto px-4 py-8 space-y-3">
        <h1 className="text-2xl">{t('collections.notFound')}</h1>
        <Link to="/" className="text-primary underline underline-offset-2">{t('collections.backToCatalogue')}</Link>
      </div>
    );
  }
  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      <div className="space-y-2">
        <p className="flex items-center gap-2 text-sm text-primary">
          <Library className="w-4 h-4" aria-hidden="true" />
          {t('collections.title')}
        </p>
        <h1 className="text-2xl">{text.title}</h1>
        {text.description && <p className="text-muted-foreground max-w-3xl whitespace-pre-line">{text.description}</p>}
      </div>
      {state.books.length === 0 ? (
        <p className="text-muted-foreground">{t('collections.empty')}</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {state.books.map((book, index) => (
            <BookCard key={book.id} book={book} eager={index < 4} />
          ))}
        </div>
      )}
      <Link to="/" className="inline-block text-primary underline underline-offset-2">{t('collections.backToCatalogue')}</Link>
    </div>
  );
}
