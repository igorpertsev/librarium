import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Heart, Library, Sparkles } from 'lucide-react';
import { booksApi, collectionsApi, usersApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import type { CollectionSummaryDto } from '../../api/types';
import { useAuth } from '../contexts/AuthContext';
import { useCollectionText } from '../utils/collections';
import { BookOfTheMonth } from './BookOfTheMonth';
import { BookShelf } from './BookShelf';

const SHELF_SIZE = 8;

const loadNewArrivals = async () =>
  (await booksApi.list({ sort: '-created_at', page: 1, page_size: SHELF_SIZE })).items.map(bookFromDto);
const loadForYou = async () => (await usersApi.recommendations()).map(bookFromDto);

function CollectionShelf({ collection }: { collection: CollectionSummaryDto }) {
  const textOf = useCollectionText();
  const { slug } = collection;
  const load = useCallback(async () => (await collectionsApi.get(slug)).books.map(bookFromDto), [slug]);
  return (
    <BookShelf
      id={`collection-${slug}`}
      title={textOf(collection).title}
      icon={Library}
      load={load}
      minimum={2}
      href={`/collections/${slug}`}
    />
  );
}

/** Shelves above the catalogue while nothing is searched or filtered: the book of the month,
 * suggestions, new arrivals and the collections the librarians feature. */
export function CatalogueShelves() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [featured, setFeatured] = useState<CollectionSummaryDto[]>([]);

  useEffect(() => {
    collectionsApi.list(true).then(setFeatured, () => setFeatured([]));
  }, []);

  return (
    <>
      <BookOfTheMonth />
      {user && <BookShelf id="for-you-title" title={t('forYou.title')} icon={Heart} load={loadForYou} minimum={2} />}
      <BookShelf id="new-arrivals-title" title={t('newArrivals.title')} icon={Sparkles} load={loadNewArrivals} reserve />
      {featured.map((collection) => (
        <CollectionShelf key={collection.id} collection={collection} />
      ))}
    </>
  );
}
