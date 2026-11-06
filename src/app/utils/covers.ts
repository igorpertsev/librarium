/**
 * Book cover lookup via the Open Library API (free, CORS-enabled).
 *
 * The edition is looked up by ISBN and its cover is referenced by *cover id*:
 * https://covers.openlibrary.org/b/id/<id>-L.jpg URLs are not rate-limited, unlike the
 * ISBN-based cover URLs, so they are safe to store and show to every visitor.
 */

export type CoverLookupResult =
  | { status: 'found'; url: string }
  | { status: 'not-found' }
  | { status: 'invalid-isbn' }
  | { status: 'error' };

export function normalizeIsbn(isbn: string): string | null {
  const compact = isbn.replace(/[\s-]/g, '').toUpperCase();
  return /^(\d{9}[\dX]|\d{13})$/.test(compact) ? compact : null;
}

export function openLibraryCoverUrl(coverId: number, size: 'S' | 'M' | 'L' = 'L'): string {
  return `https://covers.openlibrary.org/b/id/${coverId}-${size}.jpg`;
}

export async function findCoverByIsbn(isbn: string, signal?: AbortSignal): Promise<CoverLookupResult> {
  const normalized = normalizeIsbn(isbn);
  if (!normalized) return { status: 'invalid-isbn' };
  try {
    const response = await fetch(`https://openlibrary.org/isbn/${normalized}.json`, { signal });
    if (response.status === 404) return { status: 'not-found' };
    if (!response.ok) return { status: 'error' };
    const edition = (await response.json()) as { covers?: unknown };
    const coverId = Array.isArray(edition.covers)
      ? edition.covers.find((id): id is number => typeof id === 'number' && id > 0)
      : undefined;
    return coverId ? { status: 'found', url: openLibraryCoverUrl(coverId) } : { status: 'not-found' };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    return { status: 'error' };
  }
}
