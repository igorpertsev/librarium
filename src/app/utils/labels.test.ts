import { describe, expect, it } from 'vitest';
import { copyIdFrom, labelUrl } from './labels';

const ID = '3f2b8c1e-9d4a-4e6b-8f1c-2a7d5e9b0c43';

describe('labels', () => {
  it('points at the book page', () => {
    expect(labelUrl(ID, 'https://lib.example')).toBe(`https://lib.example/books/${ID}`);
  });

  it('finds the copy id in a label, a link or a typed id', () => {
    expect(copyIdFrom(`https://lib.example/books/${ID}`)).toBe(ID);
    expect(copyIdFrom(` ${ID.toUpperCase()} `)).toBe(ID);
    expect(copyIdFrom('9780306406157')).toBeNull();
  });
});
