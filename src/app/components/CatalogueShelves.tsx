import { useTranslation } from 'react-i18next';
import { Heart, Sparkles } from 'lucide-react';
import { booksApi, usersApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import { useAuth } from '../contexts/AuthContext';
import { BookShelf } from './BookShelf';

const SHELF_SIZE = 8;

const loadNewArrivals = async () =>
  (await booksApi.list({ sort: '-created_at', page: 1, page_size: SHELF_SIZE })).items.map(bookFromDto);
const loadForYou = async () => (await usersApi.recommendations()).map(bookFromDto);

/** Shelves above the catalogue while nothing is searched or filtered. */
export function CatalogueShelves() {
  const { t } = useTranslation();
  const { user } = useAuth();
  return (
    <>
      {user && <BookShelf id="for-you-title" title={t('forYou.title')} icon={Heart} load={loadForYou} minimum={2} />}
      <BookShelf id="new-arrivals-title" title={t('newArrivals.title')} icon={Sparkles} load={loadNewArrivals} reserve />
    </>
  );
}
