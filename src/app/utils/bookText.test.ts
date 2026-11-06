import { describe, expect, it } from 'vitest';
import { bookText } from './bookText';
import type { BookTranslation } from '../types';

const catcher = {
  title: 'The Catcher in the Rye',
  author: 'J. D. Salinger',
  description: 'Holden Caulfield wanders New York.',
};
const russian: BookTranslation = {
  language: 'ru',
  title: 'Над пропастью во ржи',
  author: 'Джером Сэлинджер',
  description: '',
  titleSource: 'wikidata',
  descriptionSource: 'manual',
  sourceUrl: null,
};

describe('bookText', () => {
  it('shows the original when there is no translation for the interface language', () => {
    expect(bookText({ ...catcher, translations: [russian] }, 'en')).toMatchObject({
      title: 'The Catcher in the Rye',
      originalTitle: null,
      translation: null,
    });
  });

  it('shows the translation with the original title next to it', () => {
    const text = bookText({ ...catcher, translations: [russian] }, 'ru');
    expect(text).toMatchObject({
      title: 'Над пропастью во ржи',
      author: 'Джером Сэлинджер',
      originalTitle: 'The Catcher in the Rye',
      originalAuthor: 'J. D. Salinger',
    });
    // No translated description: the original one is shown.
    expect(text.description).toBe(catcher.description);
    expect(text.descriptionTranslated).toBe(false);
  });

  it('does not repeat a title that is the same in both languages', () => {
    const text = bookText({ ...catcher, title: '1984', translations: [{ ...russian, title: '1984' }] }, 'ru-RU');
    expect(text.originalTitle).toBeNull();
  });
});
