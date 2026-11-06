import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import type { Book, BookTranslation } from '../types';

/** What a reader sees of a book: the translation for their language, if there is one. */
export interface BookText {
  title: string;
  author: string;
  description: string;
  /** The title of the edition on the shelf, when a translated title is shown instead. */
  originalTitle: string | null;
  originalAuthor: string | null;
  /** True when `description` is the translated one. */
  descriptionTranslated: boolean;
  translation: BookTranslation | null;
}

type BookFields = Pick<Book, 'title' | 'author' | 'description' | 'translations'>;

export const uiLanguage = (language: string): 'en' | 'ru' => (language.startsWith('ru') ? 'ru' : 'en');

export function bookText(book: BookFields, language: string): BookText {
  const translation = book.translations?.find((item) => item.language === uiLanguage(language)) ?? null;
  if (!translation) {
    return {
      title: book.title,
      author: book.author,
      description: book.description,
      originalTitle: null,
      originalAuthor: null,
      descriptionTranslated: false,
      translation: null,
    };
  }
  const author = translation.author || book.author;
  return {
    title: translation.title,
    author,
    description: translation.description || book.description,
    originalTitle: translation.title !== book.title ? book.title : null,
    originalAuthor: author !== book.author ? book.author : null,
    descriptionTranslated: Boolean(translation.description),
    translation,
  };
}

/** `bookText` in the current interface language. */
export function useBookText(): (book: BookFields) => BookText {
  const { i18n } = useTranslation();
  return useCallback((book: BookFields) => bookText(book, i18n.language), [i18n.language]);
}

/**
 * "English" / "английский" for a book whose language differs from the interface language;
 * null when it is the same, unknown or has no name.
 */
export function useBookLanguageName(): (code: string | null | undefined) => string | null {
  const { i18n } = useTranslation();
  return useCallback(
    (code: string | null | undefined) => {
      if (!code || code === uiLanguage(i18n.language)) return null;
      try {
        return new Intl.DisplayNames([i18n.language], { type: 'language' }).of(code) ?? null;
      } catch {
        return null;
      }
    },
    [i18n.language],
  );
}
