import { useTranslation } from 'react-i18next';
import type { CollectionSummaryDto } from '../../api/types';

/** A collection's title and description in the interface language (English as the fallback). */
export function useCollectionText() {
  const { i18n } = useTranslation();
  const russian = i18n.language.startsWith('ru');
  return (collection: Pick<CollectionSummaryDto, 'title_en' | 'title_ru' | 'description_en' | 'description_ru'>) => ({
    title: (russian && collection.title_ru) || collection.title_en,
    description: (russian && collection.description_ru) || collection.description_en,
  });
}

/** The book of the month's note in the interface language. */
export function useNoteText() {
  const { i18n } = useTranslation();
  const russian = i18n.language.startsWith('ru');
  return (note: { note_en: string | null; note_ru: string | null }) => (russian && note.note_ru) || note.note_en || '';
}
