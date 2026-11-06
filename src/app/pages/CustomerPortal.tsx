import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { BookCard } from '../components/BookCard';
import { BatchProgress } from '../components/BatchProgress';
import { AuthorBanner, SelectedTags, SeriesBanner, SeriesFilter, TagFilter } from '../components/CatalogFilters';
import { useBookText } from '../utils/bookText';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { Skeleton } from '../components/ui/skeleton';
import { Book, BookCategory } from '../types';
import { Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { booksApi } from '../../api/endpoints';
import { ApiError, toApiError } from '../../api/errors';
import { bookFromDto } from '../../api/mappers';
import { useCatalog } from '../contexts/CatalogContext';
import { errorMessage } from '../utils/apiErrors';
import type { BookListQuery } from '../../api/types';
import { parseSeriesParam, parseTagParam } from '../utils/catalogLists';

const PAGE_SIZE = 24;

type SortKey = NonNullable<BookListQuery['sort']>;
// Only keys the API allows (it validates them against an allow-list).
const SORT_OPTIONS: { value: SortKey; labelKey: string }[] = [
  // Best match for the search text; alphabetical while nothing is searched.
  { value: 'relevance', labelKey: 'catalog.sortRelevance' },
  { value: 'title', labelKey: 'catalog.sortTitle' },
  { value: '-title', labelKey: 'catalog.sortTitleDesc' },
  { value: 'author', labelKey: 'catalog.sortAuthor' },
  { value: '-publication_year', labelKey: 'catalog.sortYearNewest' },
  { value: '-created_at', labelKey: 'catalog.sortRecentlyAdded' },
];
// Offered (and the default) while one series is shown: volume 1, 2, 3...
const SERIES_SORT: { value: SortKey; labelKey: string } = { value: 'series', labelKey: 'catalog.sortSeries' };

const CATEGORIES: readonly BookCategory[] = [
  'fiction', 'non-fiction', 'children', 'young-adult', 'science', 'history', 'biography',
];
// Best match while searching, alphabetical otherwise.
const DEFAULT_SORT: SortKey = 'relevance';

// Filters live in the address bar (?q=&category=&age=&tags=a,b&series=&available=1&sort=), so reloading,
// sharing a link and the browser's Back button keep the catalogue view.
const parseCategory = (value: string | null): BookCategory | 'all' =>
  CATEGORIES.includes(value as BookCategory) ? (value as BookCategory) : 'all';
const parseSort = (value: string | null, inSeries: boolean): SortKey => {
  const options = inSeries ? [...SORT_OPTIONS, SERIES_SORT] : SORT_OPTIONS;
  if (options.some((option) => option.value === value)) return value as SortKey;
  return inSeries ? SERIES_SORT.value : DEFAULT_SORT;
};

function BookCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden" aria-hidden="true">
      <Skeleton className="aspect-[3/4] w-full rounded-none" />
      <div className="p-4 space-y-3">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <div className="flex gap-2">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-5 w-12" />
        </div>
        <Skeleton className="h-9 w-full" />
      </div>
    </div>
  );
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export default function CustomerPortal() {
  const { t, i18n } = useTranslation();
  const { version: catalogVersion } = useCatalog();
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get('q') ?? '';
  const categoryFilter = parseCategory(params.get('category'));
  const ageFilter = params.get('age') || 'all';
  const availableOnly = params.get('available') === '1';
  const tagsParam = params.get('tags');
  const tagFilter = useMemo(() => parseTagParam(tagsParam), [tagsParam]);
  const tagKey = tagFilter.join(',');
  const seriesFilter = parseSeriesParam(params.get('series'));
  const authorFilter = params.get('author')?.trim() || null;
  const textOf = useBookText();
  const languageParam = params.get('language');
  const languageFilter = languageParam && /^[a-z]{2,3}$/.test(languageParam) ? languageParam : 'all';
  const sort = parseSort(params.get('sort'), seriesFilter !== null);
  const defaultSort: SortKey = seriesFilter ? SERIES_SORT.value : DEFAULT_SORT;
  const sortOptions = seriesFilter ? [SERIES_SORT, ...SORT_OPTIONS] : SORT_OPTIONS;
  const [searchQuery, setSearchQuery] = useState(urlQuery);
  const [ageRanges, setAgeRanges] = useState<string[]>([]);
  const [languages, setLanguages] = useState<string[]>([]);
  const languageName = (code: string) => {
    try {
      return new Intl.DisplayNames([i18n.language], { type: 'language' }).of(code) ?? code;
    } catch {
      return code;
    }
  };

  /** Changes filters in the URL; `null` removes a parameter (its default). */
  const updateParams = useCallback(
    (changes: Record<string, string | null>, options: { replace?: boolean } = {}) => {
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      }, options);
    },
    [setParams],
  );

  const [books, setBooks] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  const search = useDebounced(searchQuery.trim(), 300);

  // The search text that the box and the URL last agreed on.
  const syncedQuery = useRef(urlQuery);
  // Typing updates the URL (without a history entry per keystroke)...
  useEffect(() => {
    if (search === syncedQuery.current) return;
    syncedQuery.current = search;
    updateParams({ q: search || null }, { replace: true });
  }, [search, updateParams]);
  // ...and Back/Forward put the URL's search text back into the box.
  useEffect(() => {
    if (urlQuery === syncedQuery.current) return;
    syncedQuery.current = urlQuery;
    setSearchQuery(urlQuery);
  }, [urlQuery]);

  const loadPage = useCallback(
    async (pageToLoad: number) => {
      requestRef.current?.abort();
      const controller = new AbortController();
      requestRef.current = controller;
      setIsLoading(true);
      setError(null);
      try {
        const result = await booksApi.list(
          {
            page: pageToLoad,
            page_size: PAGE_SIZE,
            q: urlQuery || undefined,
            category: categoryFilter === 'all' ? undefined : categoryFilter,
            age_range: ageFilter === 'all' ? undefined : ageFilter,
            available: availableOnly ? true : undefined,
            tags: tagKey || undefined,
            series: seriesFilter ?? undefined,
            language: languageFilter === 'all' ? undefined : languageFilter,
            author: authorFilter ?? undefined,
            sort,
          },
          controller.signal,
        );
        const mapped = result.items.map(bookFromDto);
        setBooks((prev) => (pageToLoad === 1 ? mapped : [...prev, ...mapped]));
        setTotal(result.total);
        setPage(pageToLoad);
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return;
        setError(toApiError(e));
      } finally {
        if (requestRef.current === controller) setIsLoading(false);
      }
    },
    [urlQuery, categoryFilter, ageFilter, availableOnly, tagKey, seriesFilter, languageFilter, authorFilter, sort],
  );

  // Reload from the first page when filters change or availability may have changed.
  useEffect(() => {
    loadPage(1);
    return () => requestRef.current?.abort();
  }, [loadPage, catalogVersion]);

  // New filters (e.g. a series or tag link on a card) show their results from the top.
  useEffect(() => {
    // The list scrolls on its own on tall screens; otherwise the page does.
    resultsRef.current?.scrollTo({ top: 0 });
    window.scrollTo({ top: 0 });
  }, [loadPage]);

  useEffect(() => {
    booksApi.ageRanges().then(setAgeRanges).catch(() => setAgeRanges([]));
    booksApi.languages().then(setLanguages).catch(() => setLanguages([]));
  }, [catalogVersion]);

  const hasMore = books.length < total;

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const bottom = e.currentTarget.scrollHeight - e.currentTarget.scrollTop <= e.currentTarget.clientHeight + 100;
    if (bottom && hasMore && !isLoading && !error) {
      loadPage(page + 1);
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="bg-card border-b border-border">
        <div className="container mx-auto px-4 py-6">
          <h1 className="mb-6">{t('home.availableBooks')}</h1>

          <BatchProgress />

          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
            <div className="space-y-2 md:col-span-3 lg:col-span-1">
              <Label htmlFor="search">{t('home.search')}</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="search"
                  placeholder={t('home.search')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="category">{t('bookForm.category')}</Label>
              <Select value={categoryFilter} onValueChange={(value) => updateParams({ category: value === 'all' ? null : value })}>
                <SelectTrigger id="category">
                  <SelectValue placeholder={t('home.allCategories')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('home.allCategories')}</SelectItem>
                  <SelectItem value="fiction">{t('categories.fiction')}</SelectItem>
                  <SelectItem value="non-fiction">{t('categories.non-fiction')}</SelectItem>
                  <SelectItem value="children">{t('categories.children')}</SelectItem>
                  <SelectItem value="young-adult">{t('categories.young-adult')}</SelectItem>
                  <SelectItem value="science">{t('categories.science')}</SelectItem>
                  <SelectItem value="history">{t('categories.history')}</SelectItem>
                  <SelectItem value="biography">{t('categories.biography')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="age">{t('home.ageRange')}</Label>
              <Select value={ageFilter} onValueChange={(value) => updateParams({ age: value === 'all' ? null : value })}>
                <SelectTrigger id="age">
                  <SelectValue placeholder={t('home.allAges')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('home.allAges')}</SelectItem>
                  {ageRanges.map(age => (
                    <SelectItem key={age} value={age}>{age}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="tag-filter">{t('tags.label')}</Label>
              <TagFilter
                id="tag-filter"
                selected={tagFilter}
                onChange={(slugs) => updateParams({ tags: slugs.join(',') || null })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="series-filter">{t('series.label')}</Label>
              <SeriesFilter
                id="series-filter"
                value={seriesFilter}
                // The series' own order replaces a sort chosen for the whole catalogue.
                onChange={(id) => updateParams({ series: id, sort: null })}
              />
            </div>
          </div>

          <SelectedTags
            selected={tagFilter}
            onChange={(slugs) => updateParams({ tags: slugs.join(',') || null })}
          />

          <div className="flex flex-wrap items-center justify-between gap-4 mt-4">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
              <div className="flex items-center gap-2">
                <Switch id="available-only" checked={availableOnly} onCheckedChange={(checked) => updateParams({ available: checked ? '1' : null })} />
                <Label htmlFor="available-only">{t('catalog.availableOnly')}</Label>
              </div>
              {languages.length > 1 && (
                <div className="flex items-center gap-2">
                  <Label htmlFor="language-filter" className="whitespace-nowrap">{t('catalog.language')}</Label>
                  <Select
                    value={languageFilter}
                    onValueChange={(value) => updateParams({ language: value === 'all' ? null : value })}
                  >
                    <SelectTrigger id="language-filter" className="w-44">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('catalog.allLanguages')}</SelectItem>
                      {languages.map((code) => (
                        <SelectItem key={code} value={code}>{languageName(code)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="sort" className="whitespace-nowrap">{t('catalog.sortBy')}</Label>
              <Select value={sort} onValueChange={(value) => updateParams({ sort: value === defaultSort ? null : value })}>
                <SelectTrigger id="sort" className="w-56">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {sortOptions.map(({ value, labelKey }) => (
                    <SelectItem key={value} value={value}>{t(labelKey)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </div>

      <div ref={resultsRef} className="flex-1 overflow-y-auto" onScroll={handleScroll}>
        <div className="container mx-auto px-4 py-6">
          {authorFilter && (
            <AuthorBanner
              // The name as the reader sees it on the cards (translated when possible).
              name={books[0] ? textOf(books[0]).author : authorFilter}
              total={total}
              onClear={() => updateParams({ author: null })}
            />
          )}
          {seriesFilter && (
            <SeriesBanner
              seriesId={seriesFilter}
              onClear={() => updateParams({ series: null, sort: null })}
            />
          )}
          <p className="text-muted-foreground mb-4">
            {t('home.showingCount', { shown: books.length, total })}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {books.map(book => (
              <BookCard key={book.id} book={book} />
            ))}
            {isLoading && books.length === 0 &&
              Array.from({ length: 8 }, (_, i) => <BookCardSkeleton key={i} />)}
          </div>

          {error && (
            <div className="text-center py-8 space-y-3">
              <p className="text-destructive">{errorMessage(t, error)}</p>
              <Button variant="outline" onClick={() => loadPage(books.length > 0 ? page + 1 : 1)}>
                {t('common.retry')}
              </Button>
            </div>
          )}

          {isLoading && books.length > 0 && (
            <div role="status" className="text-center py-8">
              <p className="text-muted-foreground">{t('common.loading')}</p>
            </div>
          )}

          {!isLoading && !error && books.length === 0 && (
            <div className="text-center py-12">
              <p className="text-muted-foreground">{t('home.noResults')}</p>
            </div>
          )}

          {!isLoading && !error && hasMore && (
            <div className="text-center py-8">
              <p className="text-muted-foreground">{t('home.scrollForMore')}</p>
              <Button variant="outline" className="mt-3" onClick={() => loadPage(page + 1)}>
                {t('catalog.loadMore')}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
