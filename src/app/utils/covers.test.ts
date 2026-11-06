import { describe, expect, it } from 'vitest';
import { coverOfSize } from './covers';

describe('coverOfSize', () => {
  it('switches Open Library covers to another size', () => {
    expect(coverOfSize('https://covers.openlibrary.org/b/id/15162569-L.jpg', 'M')).toBe(
      'https://covers.openlibrary.org/b/id/15162569-M.jpg',
    );
    expect(coverOfSize('https://covers.openlibrary.org/b/isbn/9780547928227-M.jpg', 'S')).toBe(
      'https://covers.openlibrary.org/b/isbn/9780547928227-S.jpg',
    );
  });

  it('leaves other images alone', () => {
    expect(coverOfSize('https://images.example.com/cover-L.jpg', 'M')).toBe('https://images.example.com/cover-L.jpg');
    expect(coverOfSize('', 'M')).toBe('');
  });
});
