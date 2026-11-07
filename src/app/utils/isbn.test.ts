import { describe, expect, it } from 'vitest';
import { isIsbn13 } from './isbn';

describe('isIsbn13', () => {
  it('accepts ISBN barcodes with a correct check digit', () => {
    expect(isIsbn13('9780547928227')).toBe(true);
    expect(isIsbn13('9791032305690')).toBe(true);
  });

  it('rejects other barcodes and wrong check digits', () => {
    expect(isIsbn13('9780547928228')).toBe(false); // check digit
    expect(isIsbn13('4006381333931')).toBe(false); // an EAN that is not a book
    expect(isIsbn13('978054792822')).toBe(false); // too short
  });
});
