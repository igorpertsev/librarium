import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Check, ChevronsUpDown, Library, ShoppingCart, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from './ui/button';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './ui/command';
import { booksApi, catalogApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import { ApiError, toApiError } from '../../api/errors';
import type { SeriesDto } from '../../api/types';
import { useCart } from '../contexts/CartContext';
import { useCatalog } from '../contexts/CatalogContext';
import type { Book } from '../types';
import { errorMessage } from '../utils/apiErrors';
import {
  MAX_TAG_FILTERS,
  useSeriesList,
  useSeriesLabel,
  useTagList,
  useTagName,
} from '../utils/catalogLists';

// Looks like the Select boxes next to it (category, age range).
const filterTriggerClass =
  'border-input bg-input-background dark:bg-input/30 dark:hover:bg-input/50 flex h-9 w-full items-center ' +
  'justify-between gap-2 rounded-md border px-3 py-2 text-sm whitespace-nowrap outline-none ' +
  'transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] ' +
  '[&_svg]:shrink-0 [&_svg]:text-muted-foreground';

const chipClass =
  'inline-flex items-center rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground ' +
  'hover:bg-secondary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/** Multi-select of tags; a book must have every selected tag. */
export function TagFilter({
  id,
  selected,
  onChange,
}: {
  id: string;
  selected: string[];
  onChange: (slugs: string[]) => void;
}) {
  const { t } = useTranslation();
  const tagName = useTagName();
  const { items: tags } = useTagList();
  const [open, setOpen] = useState(false);
  // Tags without books cannot narrow anything down; selected ones stay so they can be removed.
  const options = tags
    .filter((tag) => tag.book_count > 0 || selected.includes(tag.slug))
    .sort((a, b) => tagName(a).localeCompare(tagName(b)));
  const toggle = (slug: string) =>
    onChange(
      selected.includes(slug)
        ? selected.filter((s) => s !== slug)
        : [...selected, slug].slice(0, MAX_TAG_FILTERS),
    );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        id={id}
        role="combobox"
        aria-expanded={open}
        className={filterTriggerClass}
      >
        <span className="truncate">
          {selected.length > 0 ? t('tags.selected', { count: selected.length }) : t('tags.all')}
        </span>
        <ChevronsUpDown className="w-4 h-4 opacity-50" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent aria-label={t('tags.label')} className="w-72 p-0" align="start">
        <Command>
          <CommandInput placeholder={t('tags.search')} />
          <CommandList>
            <CommandEmpty>{t('tags.noneFound')}</CommandEmpty>
            <CommandGroup>
              {options.map((tag) => {
                const checked = selected.includes(tag.slug);
                return (
                  <CommandItem
                    key={tag.slug}
                    value={`${tag.slug} ${tag.name_en} ${tag.name_ru}`}
                    onSelect={() => toggle(tag.slug)}
                    data-checked={checked}
                  >
                    <Check
                      className={`w-4 h-4 ${checked ? 'opacity-100' : 'opacity-0'}`}
                      aria-hidden="true"
                    />
                    <span className="flex-1">{tagName(tag)}</span>
                    {checked && <span className="sr-only">{t('tags.isSelected')}</span>}
                    <span className="text-xs text-muted-foreground">{tag.book_count}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/** The selected tags as removable chips under the filters. */
export function SelectedTags({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (slugs: string[]) => void;
}) {
  const { t } = useTranslation();
  const tagName = useTagName();
  const { items: tags } = useTagList();
  if (selected.length === 0) return null;
  const nameOf = (slug: string) => {
    const tag = tags.find((item) => item.slug === slug);
    return tag ? tagName(tag) : slug;
  };
  return (
    <div className="flex flex-wrap items-center gap-2 mt-4" aria-label={t('tags.filterLabel')}>
      {selected.map((slug) => (
        <span key={slug} className="inline-flex items-center gap-1 rounded-full bg-primary/10 text-primary pl-3 pr-1 py-0.5 text-sm">
          {nameOf(slug)}
          <button
            type="button"
            onClick={() => onChange(selected.filter((s) => s !== slug))}
            aria-label={t('tags.remove', { name: nameOf(slug) })}
            className="rounded-full p-0.5 hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        </span>
      ))}
      {selected.length > 1 && (
        <Button variant="link" size="sm" className="h-auto px-1" onClick={() => onChange([])}>
          {t('tags.clear')}
        </Button>
      )}
    </div>
  );
}

/** Single-select combobox of series that have books. */
export function SeriesFilter({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string | null;
  onChange: (seriesId: string | null) => void;
}) {
  const { t } = useTranslation();
  const { items: series } = useSeriesList();
  const [open, setOpen] = useState(false);
  const current = series.find((item) => item.id === value);
  const options = series.filter((item) => item.book_count > 0 || item.id === value);
  const pick = (seriesId: string | null) => {
    onChange(seriesId);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        id={id}
        role="combobox"
        aria-expanded={open}
        className={filterTriggerClass}
      >
        <span className="truncate">{current?.name ?? (value ? t('series.one') : t('series.all'))}</span>
        <ChevronsUpDown className="w-4 h-4 opacity-50" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent aria-label={t('series.label')} className="w-80 p-0" align="start">
        <Command>
          <CommandInput placeholder={t('series.search')} />
          <CommandList>
            <CommandEmpty>{t('series.noneFound')}</CommandEmpty>
            <CommandGroup>
              <CommandItem value={`-all- ${t('series.all')}`} onSelect={() => pick(null)}>
                <Check className={`w-4 h-4 ${value ? 'opacity-0' : 'opacity-100'}`} aria-hidden="true" />
                {t('series.all')}
              </CommandItem>
              {options.map((item) => (
                <CommandItem key={item.id} value={`${item.id} ${item.name}`} onSelect={() => pick(item.id)}>
                  <Check
                    className={`w-4 h-4 ${item.id === value ? 'opacity-100' : 'opacity-0'}`}
                    aria-hidden="true"
                  />
                  <span className="flex-1">{item.name}</span>
                  <span className="text-xs text-muted-foreground">{item.book_count}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/** Above the results while one series is shown: its name and "take the whole series". */
export function SeriesBanner({ seriesId, onClear }: { seriesId: string; onClear: () => void }) {
  const { t } = useTranslation();
  const { version } = useCatalog();
  const { addBookToCart, isBookInCart } = useCart();
  const [series, setSeries] = useState<SeriesDto | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    catalogApi
      .getSeries(seriesId)
      .then((data) => {
        if (!current) return;
        setSeries(data);
        setError(null);
      })
      .catch((e) => current && setError(toApiError(e)));
    return () => {
      current = false;
    };
  }, [seriesId, version]);

  const takeAll = async () => {
    setBusy(true);
    try {
      // One entry per title, represented by a copy that can be borrowed now.
      const page = await booksApi.list({
        series: seriesId,
        available: true,
        sort: 'series',
        page_size: 100,
      });
      const books: Book[] = page.items.map(bookFromDto).filter((book) => !isBookInCart(book.id));
      if (page.items.length === 0) {
        toast.info(t('series.noneAvailable'));
        return;
      }
      if (books.length === 0) {
        toast.info(t('series.allInCart'));
        return;
      }
      let added = 0;
      let failure: ApiError | null = null;
      for (const book of books) {
        const result = await addBookToCart(book);
        if (result.ok) added += 1;
        else failure ??= result.error;
      }
      if (added > 0) toast.success(t('series.added', { count: added }));
      if (failure) toast.error(errorMessage(t, failure));
    } catch (e) {
      toast.error(errorMessage(t, toApiError(e)));
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <div className="rounded-lg border border-border p-4 mb-4 flex items-center justify-between gap-3">
        <p className="text-destructive">{errorMessage(t, error)}</p>
        <Button variant="outline" size="sm" onClick={onClear}>{t('series.showAll')}</Button>
      </div>
    );
  }

  return (
    <section
      aria-labelledby="series-banner-title"
      className="rounded-lg border border-border bg-muted/40 p-4 mb-4 flex flex-wrap items-start justify-between gap-4"
    >
      <div className="flex gap-3 min-w-0">
        <Library className="w-6 h-6 text-primary shrink-0 mt-1" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{t('series.label')}</p>
          <h2 id="series-banner-title" className="text-lg">{series?.name ?? '…'}</h2>
          {series && (
            <p className="text-sm text-muted-foreground">{t('series.titles', { count: series.book_count })}</p>
          )}
          {series?.description && (
            <p className="text-sm text-muted-foreground mt-2 max-w-2xl">{series.description}</p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={takeAll} disabled={busy || !series}>
          <ShoppingCart className="w-4 h-4 mr-2" aria-hidden="true" />
          {t('series.takeAll')}
        </Button>
        <Button variant="ghost" onClick={onClear}>
          <X className="w-4 h-4 mr-2" aria-hidden="true" />
          {t('series.showAll')}
        </Button>
      </div>
    </section>
  );
}

/** "Harry Potter, book 3" linking to the series in the catalogue. */
export function SeriesLink({
  book,
  className = '',
  onNavigate,
}: {
  book: Pick<Book, 'series' | 'seriesPosition'>;
  className?: string;
  onNavigate?: () => void;
}) {
  const { t } = useTranslation();
  const label = useSeriesLabel()(book);
  if (!book.series || !label) return null;
  return (
    <Link
      to={{ pathname: '/', search: `?series=${book.series.id}` }}
      onClick={onNavigate}
      className={`inline-flex items-center gap-1 text-primary hover:underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm ${className}`}
      aria-label={t('series.showSeries', { label })}
    >
      <Library className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
      <span className="truncate">{label}</span>
    </Link>
  );
}

/** Tag chips linking to the catalogue filtered by that tag. */
export function TagChips({
  tags,
  limit,
  onNavigate,
}: {
  tags: Book['tags'];
  limit?: number;
  onNavigate?: () => void;
}) {
  const { t } = useTranslation();
  const tagName = useTagName();
  if (!tags || tags.length === 0) return null;
  const shown = limit ? tags.slice(0, limit) : tags;
  const hidden = tags.length - shown.length;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label={t('tags.label')}>
      {shown.map((tag) => (
        <li key={tag.slug}>
          <Link
            to={{ pathname: '/', search: `?tags=${tag.slug}` }}
            onClick={onNavigate}
            className={chipClass}
            aria-label={t('tags.showTag', { name: tagName(tag) })}
          >
            {tagName(tag)}
          </Link>
        </li>
      ))}
      {hidden > 0 && (
        <li className="text-xs text-muted-foreground self-center" title={tags.slice(shown.length).map(tagName).join(', ')}>
          {t('tags.more', { count: hidden })}
        </li>
      )}
    </ul>
  );
}
