import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { catalogApi } from '../../api/endpoints';
import type { SeriesDto, TagDto } from '../../api/types';
import { useCatalog } from '../contexts/CatalogContext';
import type { Book, BookTag } from '../types';

type NamedTag = Pick<BookTag, 'nameEn' | 'nameRu'> | Pick<TagDto, 'name_en' | 'name_ru'>;

/** A tag's name in the reader's language (Russian or English). */
export function useTagName(): (tag: NamedTag) => string {
  const { i18n } = useTranslation();
  const russian = i18n.language.startsWith('ru');
  return useCallback(
    (tag: NamedTag) =>
      'nameEn' in tag ? (russian ? tag.nameRu : tag.nameEn) : russian ? tag.name_ru : tag.name_en,
    [russian],
  );
}

type NamedSeries = { name: string; nameEn?: string | null; nameRu?: string | null } | {
  name: string;
  name_en?: string | null;
  name_ru?: string | null;
};

/** A series' name in the reader's language ("Гарри Поттер"), else its own name. */
export function useSeriesName(): (series: NamedSeries) => string {
  const { i18n } = useTranslation();
  const russian = i18n.language.startsWith('ru');
  return useCallback(
    (series: NamedSeries) => {
      const names =
        'nameEn' in series || 'nameRu' in series
          ? { en: (series as { nameEn?: string | null }).nameEn, ru: (series as { nameRu?: string | null }).nameRu }
          : { en: (series as { name_en?: string | null }).name_en, ru: (series as { name_ru?: string | null }).name_ru };
      return (russian ? names.ru : names.en) || series.name;
    },
    [russian],
  );
}

/** "3", "1.5": volume numbers are usually whole. */
export function formatVolume(position: number, language: string): string {
  return Number.isInteger(position) ? String(position) : position.toLocaleString(language);
}

/** "Harry Potter, book 3" or just "Harry Potter"; null when the book is not in a series. */
export function useSeriesLabel(): (book: Pick<Book, 'series' | 'seriesPosition'>) => string | null {
  const { t, i18n } = useTranslation();
  const seriesName = useSeriesName();
  return useCallback(
    (book) => {
      if (!book.series) return null;
      const name = seriesName(book.series);
      if (book.seriesPosition == null) return name;
      return t('series.volume', { name, n: formatVolume(book.seriesPosition, i18n.language) });
    },
    [t, i18n.language, seriesName],
  );
}

/** Loads a list once per catalogue version (admin edits bump it). */
function useCatalogList<T>(load: () => Promise<T[]>): { items: T[]; loaded: boolean } {
  const { version } = useCatalog();
  const [state, setState] = useState<{ items: T[]; loaded: boolean }>({ items: [], loaded: false });
  useEffect(() => {
    let current = true;
    load()
      .then((items) => current && setState({ items, loaded: true }))
      .catch(() => current && setState((prev) => ({ ...prev, loaded: true })));
    return () => {
      current = false;
    };
  }, [load, version]);
  return state;
}

const loadTags = () => catalogApi.tags();
const loadSeries = () => catalogApi.series();

/** Every tag with the number of titles that have it. */
export const useTagList = () => useCatalogList<TagDto>(loadTags);
/** Series in name order (up to 200) with their number of titles. */
export const useSeriesList = () => useCatalogList<SeriesDto>(loadSeries);

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;
export const MAX_TAG_FILTERS = 10;

/** Tag slugs from the `?tags=a,b` URL parameter (invalid ones are ignored). */
export function parseTagParam(value: string | null): string[] {
  if (!value) return [];
  const slugs = value.split(',').filter((slug) => SLUG.test(slug));
  return [...new Set(slugs)].slice(0, MAX_TAG_FILTERS);
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const parseSeriesParam = (value: string | null): string | null =>
  value && UUID.test(value) ? value : null;
