import { useState, useMemo } from 'react';
import { BookCard } from '../components/BookCard';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { mockBooks } from '../data/mockBooks';
import { BookCategory } from '../types';
import { Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function CustomerPortal() {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<BookCategory | 'all'>('all');
  const [ageFilter, setAgeFilter] = useState<string>('all');
  const [displayCount, setDisplayCount] = useState(12);

  const filteredBooks = useMemo(() => {
    return mockBooks.filter(book => {
      const matchesSearch =
        book.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        book.author.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesCategory = categoryFilter === 'all' || book.category === categoryFilter;

      const matchesAge = ageFilter === 'all' || book.ageRange === ageFilter;

      return matchesSearch && matchesCategory && matchesAge;
    });
  }, [searchQuery, categoryFilter, ageFilter]);

  const displayedBooks = filteredBooks.slice(0, displayCount);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const bottom = e.currentTarget.scrollHeight - e.currentTarget.scrollTop <= e.currentTarget.clientHeight + 100;
    if (bottom && displayCount < filteredBooks.length) {
      setDisplayCount(prev => Math.min(prev + 8, filteredBooks.length));
    }
  };

  const ageRanges = Array.from(new Set(mockBooks.map(b => b.ageRange)));

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
            Showing {displayedBooks.length} of {filteredBooks.length} books
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {displayedBooks.map(book => (
              <BookCard key={book.id} book={book} />
            ))}
          </div>

          {displayedBooks.length === 0 && (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No books found matching your criteria.</p>
            </div>
          )}

          {displayCount < filteredBooks.length && (
            <div className="text-center py-8">
              <p className="text-muted-foreground">Scroll down to load more books...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
