import type { BookDto, CartDto } from '../api/types';

/** A complete BookRead DTO; override only what a test cares about. */
export function bookDto(overrides: Partial<BookDto> = {}): BookDto {
  return {
    id: 'book-1',
    title: 'The Hobbit',
    author: 'J.R.R. Tolkien',
    description: 'There and back again.',
    category: 'fiction',
    age_range: '8+',
    status: 'available',
    cover_url: 'https://covers.example.com/hobbit.jpg',
    image_urls: [],
    isbn: '9780547928227',
    language: 'en',
    publication_year: 1937,
    is_active: true,
    is_reserved: false,
    is_available: true,
    available_from: null,
    copies: 1,
    copies_available: 1,
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:00Z',
    ...overrides,
  };
}

export function cartDto(books: BookDto[], booksPerBatch = 2): CartDto {
  return {
    items: books.map((book, index) => ({
      book,
      added_at: '2026-11-01T10:00:00Z',
      batch_number: Math.floor(index / booksPerBatch) + 1,
      in_complete_batch: index < Math.floor(books.length / booksPerBatch) * booksPerBatch,
    })),
    item_count: books.length,
    books_per_batch: booksPerBatch,
    price_per_batch: '10.00',
    currency: 'USD',
    complete_batches: Math.floor(books.length / booksPerBatch),
    orderable_item_count: Math.floor(books.length / booksPerBatch) * booksPerBatch,
    total_amount: (Math.floor(books.length / booksPerBatch) * 10).toFixed(2),
    has_unavailable_items: books.some((b) => !b.is_available),
  };
}
