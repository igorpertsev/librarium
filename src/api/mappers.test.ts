import { describe, expect, it } from 'vitest';
import { bookDto, cartDto } from '../test/fixtures';
import { bookFormToDto, bookFromDto, cartFromDto, contactsToDto, toMoney } from './mappers';

describe('toMoney', () => {
  it('parses decimal strings and falls back to 0', () => {
    expect(toMoney('15.99')).toBe(15.99);
    expect(toMoney(3)).toBe(3);
    expect(toMoney('not a number')).toBe(0);
  });
});

describe('bookFromDto', () => {
  it('maps snake_case fields and uses the cover when there is no gallery', () => {
    const book = bookFromDto(bookDto({ available_from: '2026-12-06', is_available: false }));
    expect(book).toMatchObject({
      ageRange: '8+',
      publishedYear: 1937,
      coverImage: 'https://covers.example.com/hobbit.jpg',
      images: ['https://covers.example.com/hobbit.jpg'],
      isAvailable: false,
      availableFrom: '2026-12-06',
    });
  });

  it('keeps the gallery and tolerates missing optional values', () => {
    const book = bookFromDto(
      bookDto({ cover_url: null, image_urls: ['a.jpg', 'b.jpg'], isbn: null, publication_year: null }),
    );
    expect(book.coverImage).toBe('');
    expect(book.images).toEqual(['a.jpg', 'b.jpg']);
    expect(book.isbn).toBe('');
    expect(book.publishedYear).toBe(0);
  });

  it('maps tags and the series with the volume number', () => {
    const book = bookFromDto(
      bookDto({
        tags: [{ slug: 'fantasy', name_en: 'Fantasy', name_ru: 'Фэнтези' }],
        series: { id: 'series-1', name: 'Middle-earth', name_en: null, name_ru: 'Средиземье' },
        series_position: 1,
      }),
    );
    expect(book.tags).toEqual([{ slug: 'fantasy', nameEn: 'Fantasy', nameRu: 'Фэнтези' }]);
    expect(book.series).toEqual({ id: 'series-1', name: 'Middle-earth', nameEn: null, nameRu: 'Средиземье' });
    expect(book.seriesPosition).toBe(1);
  });
});

describe('bookFormToDto', () => {
  const form = {
    title: 'Dune',
    author: 'Frank Herbert',
    category: 'fiction' as const,
    ageRange: '14+',
    status: 'pending' as const,
    condition: 'worn' as const,
    conditionNote: ' Spine creased ',
    coverImage: '  https://img.example.com/dune.jpg ',
    images: [' ', 'https://img.example.com/dune-2.jpg '],
    description: 'Spice.',
    isbn: '  ',
    publishedYear: Number.NaN,
    tags: ['science-fiction'],
    seriesName: '  ',
    seriesPosition: 2,
    language: 'en',
    translations: [],
  };

  it('trims URLs, drops empty values and never stores the UI-only "pending" status', () => {
    expect(bookFormToDto(form)).toEqual({
      title: 'Dune',
      author: 'Frank Herbert',
      category: 'fiction',
      age_range: '14+',
      status: 'available',
      condition: 'worn',
      condition_note: 'Spine creased',
      cover_url: 'https://img.example.com/dune.jpg',
      image_urls: ['https://img.example.com/dune-2.jpg'],
      description: 'Spice.',
      isbn: null,
      publication_year: null,
      tags: ['science-fiction'],
      series_id: null,
      language: 'en',
      translations: [],
    });
  });

  it('sends translations with a title, never one into the book\'s own language', () => {
    const translation = {
      language: 'ru' as const,
      title: ' Дюна ',
      author: 'Фрэнк Герберт',
      description: '',
      titleSource: 'wikidata' as const,
      descriptionSource: 'wikipedia' as const,
      sourceUrl: 'https://ru.wikipedia.org/wiki/Дюна',
    };
    const dto = bookFormToDto({
      ...form,
      translations: [translation, { ...translation, language: 'en', title: 'Dune' }, { ...translation, title: ' ' }],
    });
    // Without a description there is nothing to attribute to Wikipedia.
    expect(dto.translations).toEqual([
      {
        language: 'ru',
        title: 'Дюна',
        author: 'Фрэнк Герберт',
        description: '',
        title_source: 'wikidata',
        description_source: 'manual',
        source_url: null,
      },
    ]);
  });

  it('sends the series by name with its volume and Open Library key', () => {
    expect(
      bookFormToDto({ ...form, seriesName: ' Dune ', seriesOpenlibraryKey: 'OL1L' }),
    ).toMatchObject({
      series_name: 'Dune',
      series_position: 2,
      series_openlibrary_key: 'OL1L',
    });
    expect(bookFormToDto({ ...form, seriesName: 'Dune', seriesPosition: 0 })).toMatchObject({
      series_name: 'Dune',
      series_position: null,
    });
  });

  it('uses the cover as the only image when the gallery is empty', () => {
    expect(bookFormToDto({ ...form, images: [] }).image_urls).toEqual([
      'https://img.example.com/dune.jpg',
    ]);
  });
});

describe('cartFromDto', () => {
  it('groups items into batches and collects unavailable books', () => {
    const cart = cartFromDto(
      cartDto([
        bookDto({ id: 'a' }),
        bookDto({ id: 'b' }),
        bookDto({ id: 'c', is_available: false }),
      ]),
    );
    expect(cart.batches.map((batch) => batch.books.map((b) => b.id))).toEqual([['a', 'b'], ['c']]);
    expect(cart.batchConfig).toEqual({ booksPerBatch: 2, pricePerBatch: 10 });
    expect(cart.totalPrice).toBe(10);
    expect([...cart.unavailableBookIds]).toEqual(['c']);
  });
});

describe('contactsToDto', () => {
  it('sends null for removed contacts', () => {
    expect(contactsToDto({ telegram: '@dana', preferred: 'telegram' })).toEqual({
      whatsapp: null,
      telegram: '@dana',
      instagram: null,
      phone: null,
      preferred_contact_method: 'telegram',
    });
  });
});

describe('uploaded covers', () => {
  it('are shown from the backend and saved back as paths', async () => {
    const { mediaUrl, storedMediaUrl } = await import('./media');
    const { coverOfSize } = await import('../app/utils/covers');
    const path = '/media/covers/0123456789abcdef0123456789abcdef-L.webp';
    const shown = mediaUrl(path, 'https://api.example.com');
    expect(shown).toBe(`https://api.example.com${path}`);
    expect(coverOfSize(shown, 'S')).toBe('https://api.example.com/media/covers/0123456789abcdef0123456789abcdef-S.webp');
    expect(storedMediaUrl(shown, 'https://api.example.com')).toBe(path);
    expect(storedMediaUrl('https://covers.openlibrary.org/b/id/1-L.jpg', 'https://api.example.com')).toBe(
      'https://covers.openlibrary.org/b/id/1-L.jpg',
    );
  });
});
