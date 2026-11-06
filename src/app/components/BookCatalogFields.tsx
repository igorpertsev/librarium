import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Plus, X } from 'lucide-react';
import { buttonVariants } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './ui/command';
import type { BookFormValues } from '../../api/mappers';
import { useSeriesList, useTagList, useTagName } from '../utils/catalogLists';

/** A book has at most this many tags (the API limit). */
const MAX_BOOK_TAGS = 20;

type Fields = Pick<BookFormValues, 'tags' | 'seriesName' | 'seriesPosition' | 'seriesOpenlibraryKey'>;

/** Tags and series inputs of the admin book form. */
export function BookCatalogFields({
  value,
  onChange,
}: {
  value: Fields;
  onChange: (changes: Partial<Fields>) => void;
}) {
  const { t } = useTranslation();
  const tagName = useTagName();
  const { items: tags } = useTagList();
  const { items: series } = useSeriesList();
  const [open, setOpen] = useState(false);
  const selected = value.tags;
  const nameOf = (slug: string) => {
    const tag = tags.find((item) => item.slug === slug);
    return tag ? tagName(tag) : slug;
  };
  const toggle = (slug: string) =>
    onChange({
      tags: selected.includes(slug)
        ? selected.filter((s) => s !== slug)
        : [...selected, slug].slice(0, MAX_BOOK_TAGS),
    });
  const sorted = [...tags].sort((a, b) => tagName(a).localeCompare(tagName(b)));

  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="book-tags">{t('tags.label')}</Label>
        <div className="flex flex-wrap items-center gap-2">
          {selected.map((slug) => (
            <span
              key={slug}
              className="inline-flex items-center gap-1 rounded-full bg-secondary text-secondary-foreground pl-3 pr-1 py-0.5 text-sm"
            >
              {nameOf(slug)}
              <button
                type="button"
                onClick={() => toggle(slug)}
                aria-label={t('tags.remove', { name: nameOf(slug) })}
                className="rounded-full p-0.5 hover:bg-background/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="w-3.5 h-3.5" aria-hidden="true" />
              </button>
            </span>
          ))}
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger
              id="book-tags"
              role="combobox"
              aria-expanded={open}
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
            >
              <Plus className="w-4 h-4 mr-1" aria-hidden="true" />
              {t('tags.add')}
            </PopoverTrigger>
            <PopoverContent aria-label={t('tags.add')} className="w-72 p-0" align="start">
              <Command>
                <CommandInput placeholder={t('tags.search')} />
                <CommandList>
                  <CommandEmpty>{t('tags.noneFound')}</CommandEmpty>
                  <CommandGroup>
                    {sorted.map((tag) => {
                      const checked = selected.includes(tag.slug);
                      return (
                        <CommandItem
                          key={tag.slug}
                          value={`${tag.slug} ${tag.name_en} ${tag.name_ru}`}
                          onSelect={() => toggle(tag.slug)}
                        >
                          <Check className={`w-4 h-4 ${checked ? 'opacity-100' : 'opacity-0'}`} aria-hidden="true" />
                          <span className="flex-1">{tagName(tag)}</span>
                          {checked && <span className="sr-only">{t('tags.isSelected')}</span>}
                        </CommandItem>
                      );
                    })}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        </div>
        <p className="text-xs text-muted-foreground">{t('tags.formHint')}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_8rem] gap-4">
        <div className="space-y-2">
          <Label htmlFor="seriesName">{t('series.label')}</Label>
          <Input
            id="seriesName"
            list="series-options"
            autoComplete="off"
            placeholder={t('series.namePlaceholder')}
            value={value.seriesName}
            // A typed name no longer matches the Open Library series of an earlier lookup.
            onChange={(e) => onChange({ seriesName: e.target.value, seriesOpenlibraryKey: null })}
          />
          <datalist id="series-options">
            {series.map((item) => (
              <option key={item.id} value={item.name} />
            ))}
          </datalist>
        </div>
        <div className="space-y-2">
          <Label htmlFor="seriesPosition">{t('series.position')}</Label>
          <Input
            id="seriesPosition"
            type="number"
            min="0.5"
            step="0.5"
            disabled={!value.seriesName.trim()}
            value={value.seriesPosition ?? ''}
            onChange={(e) =>
              onChange({ seriesPosition: e.target.value === '' ? null : Number(e.target.value) })
            }
          />
        </div>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">{t('series.formHint')}</p>
    </>
  );
}
