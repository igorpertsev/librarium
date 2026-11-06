import { useState, useEffect, useRef, useCallback } from 'react';
import { BookCard } from '../components/BookCard';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Book, BookCategory } from '../types';
import { Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { booksApi } from '../../api/endpoints';
import { ApiError, toApiError } from '../../api/errors';
import { bookFromDto } from '../../api/mappers';
import { useCatalog } from '../contexts/CatalogContext';
import { errorMessage } from '../utils/apiErrors';

const PAGE_SIZE = 24;

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export default function CustomerPortal() {
  const { t } = useTranslation();
  const { version: catalogVersion } = useCatalog();
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<BookCategory | 'all'>('all');
  const [ageFilter, setAgeFilter] = useState<string>('all');
  const [ageRanges, setAgeRanges] = useState<string[]>([]);

  const [books, setBooks] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const search = useDebounced(searchQuery.trim(), 300);

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
            q: search || undefined,
            category: categoryFilter === 'all' ? undefined : categoryFilter,
            age_range: ageFilter === 'all' ? undefined : ageFilter,
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
    [search, categoryFilter, ageFilter],
  );

  // Reload from the first page when filters change or availability may have changed.
  useEffect(() => {
    loadPage(1);
    return () => requestRef.current?.abort();
  }, [loadPage, catalogVersion]);

  useEffect(() => {
    booksApi.ageRanges().then(setAgeRanges).catch(() => setAgeRanges([]));
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

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
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
              <Select value={categoryFilter} onValueChange={(value) => setCategoryFilter(value as BookCategory | 'all')}>
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
              <Select value={ageFilter} onValueChange={setAgeFilter}>
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
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto" onScroll={handleScroll}>
        <div className="container mx-auto px-4 py-6">
          <p className="text-muted-foreground mb-4">
            {t('home.showingCount', { shown: books.length, total })}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {books.map(book => (
              <BookCard key={book.id} book={book} />
            ))}
          </div>

          {error && (
            <div className="text-center py-8 space-y-3">
              <p className="text-destructive">{errorMessage(t, error)}</p>
              <Button variant="outline" onClick={() => loadPage(books.length > 0 ? page + 1 : 1)}>
                {t('common.retry')}
              </Button>
            </div>
          )}

          {isLoading && (
            <div className="text-center py-8">
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
