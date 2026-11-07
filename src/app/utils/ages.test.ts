import { describe, expect, it } from 'vitest';
import { childAge, minAge, parseForAge } from './ages';

describe('minAge', () => {
  it('reads the first number of an age range', () => {
    expect(minAge('8+')).toBe(8);
    expect(minAge('6-10')).toBe(6);
    expect(minAge(' 12 лет')).toBe(12);
    expect(minAge('')).toBeNull();
    expect(minAge('adults')).toBeNull();
    expect(minAge(undefined)).toBeNull();
  });
});

describe('childAge', () => {
  const today = new Date('2026-11-07T12:00:00Z');
  it('counts years from the birth year', () => {
    expect(childAge(2019, today)).toBe(7);
    expect(childAge(null, today)).toBeNull();
    expect(childAge(2030, today)).toBeNull();
    expect(childAge(1990, today)).toBeNull();
  });
});

describe('parseForAge', () => {
  it('accepts ages up to 18 only', () => {
    expect(parseForAge('7')).toBe(7);
    expect(parseForAge('19')).toBeNull();
    expect(parseForAge('x')).toBeNull();
    expect(parseForAge(null)).toBeNull();
  });
});
