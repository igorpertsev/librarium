import { describe, expect, it } from 'vitest';
import i18n from '../../i18n/config';
import { ApiError } from '../../api/errors';
import { errorMessage } from './apiErrors';

const t = i18n.getFixedT('en');
const error = (code: string, details: Record<string, unknown> | null = null) =>
  new ApiError(400, { code, message: 'server text', details });

describe('errorMessage', () => {
  it('translates known codes and hides unknown server messages', () => {
    expect(errorMessage(t, error('INVALID_CREDENTIALS'))).toBe('Invalid email or password');
    expect(errorMessage(t, error('SOMETHING_NEW'))).toBe('Something went wrong. Please try again.');
  });

  it('lists the books that are no longer available', () => {
    const unavailable = error('BOOK_UNAVAILABLE', {
      books: [
        { id: '1', title: 'Dune' },
        { id: '2', title: 'Emma' },
      ],
    });
    expect(errorMessage(t, unavailable)).toContain('Dune, Emma');
    expect(errorMessage(t, error('BOOK_UNAVAILABLE'))).toBe('Some books are no longer available');
  });

  it('includes the batch size for incomplete batches', () => {
    expect(errorMessage(t, error('INCOMPLETE_BATCH', { books_per_batch: 5 }))).toContain('5');
  });

  it('works in Russian', () => {
    const ru = i18n.getFixedT('ru');
    expect(errorMessage(ru, error('INVALID_CREDENTIALS'))).toBe('Неверный email или пароль');
  });
});
