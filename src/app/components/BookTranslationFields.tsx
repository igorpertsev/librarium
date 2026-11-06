import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Languages, Loader2, X } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { BookFormValues } from '../../api/mappers';
import type { BookTranslation, TranslationSource } from '../types';
import { errorMessage } from '../utils/apiErrors';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Textarea } from './ui/textarea';

type Fields = Pick<BookFormValues, 'title' | 'author' | 'description' | 'isbn' | 'language' | 'translations'>;

const NOT_SET = 'none';
const LANGUAGES = ['en', 'ru', 'fr', 'de', 'es', 'it'];

/** "https://ru.wikipedia.org/wiki/Дюна" rather than its percent-encoded form. */
function readableUrl(url: string): string {
  try {
    return decodeURI(url);
  } catch {
    return url;
  }
}

const emptyTranslation = (language: 'en' | 'ru'): BookTranslation => ({
  language,
  title: '',
  author: '',
  description: '',
  titleSource: 'manual',
  descriptionSource: 'manual',
  sourceUrl: null,
});

const SOURCE_LABELS: Record<Exclude<TranslationSource, 'manual'>, string> = {
  wikidata: 'translationForm.sourceWikidata',
  wikipedia: 'translationForm.sourceWikipedia',
  machine: 'translationForm.sourceMachine',
};

function SourceBadge({ source }: { source: TranslationSource }) {
  const { t } = useTranslation();
  if (source === 'manual') return null;
  return (
    <Badge variant={source === 'machine' ? 'secondary' : 'outline'} className="ml-2 font-normal">
      {t(SOURCE_LABELS[source])}
    </Badge>
  );
}

/** The book's language and its translation into the other interface language. */
export function BookTranslationFields({
  value,
  onChange,
}: {
  value: Fields;
  onChange: (changes: Partial<Fields>) => void;
}) {
  const { t, i18n } = useTranslation();
  const [finding, setFinding] = useState(false);
  // English books get a Russian translation and the other way round.
  const target: 'en' | 'ru' = value.language === 'ru' ? 'en' : 'ru';
  const translation = value.translations.find((item) => item.language === target) ?? emptyTranslation(target);
  const targetName = new Intl.DisplayNames([i18n.language], { type: 'language' }).of(target) ?? target;
  const languageName = (code: string) => new Intl.DisplayNames([i18n.language], { type: 'language' }).of(code) ?? code;
  const languages = value.language && !LANGUAGES.includes(value.language) ? [...LANGUAGES, value.language] : LANGUAGES;

  const save = (next: BookTranslation) =>
    onChange({ translations: [...value.translations.filter((item) => item.language !== target), next] });

  // Text a librarian types is theirs; a Wikipedia text stays attributed even when edited.
  const edit = (changes: Partial<BookTranslation>) => {
    const next = { ...translation, ...changes };
    if ('title' in changes) next.titleSource = 'manual';
    if ('description' in changes && translation.descriptionSource !== 'wikipedia') next.descriptionSource = 'manual';
    if ('description' in changes && !changes.description?.trim()) {
      next.descriptionSource = 'manual';
      next.sourceUrl = null;
    }
    save(next);
  };

  const find = async () => {
    setFinding(true);
    const result = await runAction(() =>
      adminApi.suggestTranslation({
        target,
        title: value.title.trim(),
        author: value.author.trim(),
        description: value.description.trim(),
        isbn: value.isbn.trim() || null,
        language: value.language || null,
        machine: true,
      }),
    );
    setFinding(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    const found = result.data;
    // Only empty fields are filled in: what the librarian wrote is kept.
    const next = { ...translation };
    let filled = false;
    if (!next.title.trim() && found.title) {
      next.title = found.title;
      next.titleSource = found.title_source ?? 'manual';
      filled = true;
    }
    if (!next.author.trim() && found.author) {
      next.author = found.author;
      filled = true;
    }
    if (!next.description.trim() && found.description) {
      next.description = found.description;
      next.descriptionSource = found.description_source ?? 'manual';
      next.sourceUrl = found.source_url;
      filled = true;
    }
    if (filled) {
      save(next);
      toast.success(t('translationForm.found'));
      if (next.titleSource === 'machine' || next.descriptionSource === 'machine') {
        toast.info(t('translationForm.checkMachine'));
      }
    } else if (found.title || found.description) {
      toast.info(t('translationForm.nothingEmpty'));
    } else {
      toast.error(found.machine_available ? t('translationForm.notFound') : t('translationForm.notFoundNoMachine'));
    }
  };

  return (
    <section aria-labelledby="translation-heading" className="space-y-4 rounded-lg border border-border p-4">
      <div className="space-y-2 sm:max-w-56">
        <Label htmlFor="bookLanguage">{t('translationForm.bookLanguage')}</Label>
        <Select
          value={value.language || NOT_SET}
          onValueChange={(code) => onChange({ language: code === NOT_SET ? '' : code })}
        >
          <SelectTrigger id="bookLanguage">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NOT_SET}>{t('translationForm.notSet')}</SelectItem>
            {languages.map((code) => (
              <SelectItem key={code} value={code}>
                {languageName(code)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="translation-heading" className="text-base">
          {t('translationForm.heading', { language: targetName })}
        </h3>
        <div className="flex flex-wrap gap-2">
          {(translation.title || translation.author || translation.description) && (
            <Button type="button" variant="ghost" size="sm" onClick={() => save(emptyTranslation(target))}>
              <X className="w-4 h-4 mr-1" aria-hidden="true" />
              {t('translationForm.clear')}
            </Button>
          )}
          <Button type="button" variant="outline" size="sm" onClick={find} disabled={finding || !value.title.trim()}>
            {finding ? (
              <Loader2 className="w-4 h-4 mr-1 animate-spin" aria-hidden="true" />
            ) : (
              <Languages className="w-4 h-4 mr-1" aria-hidden="true" />
            )}
            {t('translationForm.find')}
          </Button>
        </div>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">{t('translationForm.hint')}</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="translationTitle">
            {t('translationForm.title')}
            <SourceBadge source={translation.titleSource} />
          </Label>
          <Input
            id="translationTitle"
            lang={target}
            maxLength={500}
            value={translation.title}
            onChange={(e) => edit({ title: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="translationAuthor">{t('translationForm.author')}</Label>
          <Input
            id="translationAuthor"
            lang={target}
            maxLength={300}
            value={translation.author}
            onChange={(e) => edit({ author: e.target.value })}
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="translationDescription">
          {t('translationForm.description')}
          <SourceBadge source={translation.descriptionSource} />
        </Label>
        <Textarea
          id="translationDescription"
          lang={target}
          rows={4}
          maxLength={10000}
          value={translation.description}
          onChange={(e) => edit({ description: e.target.value })}
        />
        {translation.descriptionSource === 'wikipedia' && translation.sourceUrl && (
          <p className="text-xs text-muted-foreground">
            {t('translationForm.wikipediaNote')}{' '}
            <a
              href={translation.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 break-all"
            >
              {readableUrl(translation.sourceUrl)}
            </a>
          </p>
        )}
      </div>
    </section>
  );
}
