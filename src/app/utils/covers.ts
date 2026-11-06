/**
 * Book details by ISBN for the admin form. The backend asks Open Library
 * (GET /admin/isbn/{isbn}), so the browser only ever talks to our own API.
 */
import { adminApi } from '../../api/endpoints';
import type { BookLookupDto } from '../../api/types';
import { ApiError } from '../../api/errors';

export type IsbnLookupResult =
  | { status: 'found'; details: BookLookupDto }
  | { status: 'not-found' }
  | { status: 'invalid-isbn' }
  | { status: 'error' };

export function normalizeIsbn(isbn: string): string | null {
  const compact = isbn.replace(/[\s-]/g, '').toUpperCase();
  return /^(\d{9}[\dX]|\d{13})$/.test(compact) ? compact : null;
}

export async function lookupBookByIsbn(isbn: string): Promise<IsbnLookupResult> {
  const normalized = normalizeIsbn(isbn);
  if (!normalized) return { status: 'invalid-isbn' };
  try {
    return { status: 'found', details: await adminApi.lookupIsbn(normalized) };
  } catch (error) {
    if (error instanceof ApiError && error.code === 'ISBN_NOT_FOUND') return { status: 'not-found' };
    return { status: 'error' };
  }
}

const OPEN_LIBRARY_COVER = /^(https:\/\/covers\.openlibrary\.org\/b\/(?:id|isbn|olid)\/[^/?#]+)-[SML]\.jpg$/;

/**
 * The same Open Library cover in another size: S (small), M (medium, enough for cards) or L
 * (large, for the book dialog). Other image URLs are returned unchanged.
 */
export function coverOfSize(url: string, size: 'S' | 'M' | 'L'): string {
  const match = OPEN_LIBRARY_COVER.exec(url);
  return match ? `${match[1]}-${size}.jpg` : url;
}
