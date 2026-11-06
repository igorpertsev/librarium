import { act, renderHook } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import i18n from '../../i18n/config';
import { daysUntil, parseDate, useFormat } from './format';

describe('parseDate', () => {
  it('reads date-only values as local calendar days', () => {
    const date = parseDate('2026-12-06');
    expect(date && [date.getFullYear(), date.getMonth(), date.getDate(), date.getHours()]).toEqual([
      2026, 11, 6, 0,
    ]);
  });

  it('returns null for invalid input', () => {
    expect(parseDate('not a date')).toBeNull();
  });
});

describe('daysUntil', () => {
  beforeAll(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 6, 23, 30)); // 6 Nov 2026, late evening
  });
  afterAll(() => vi.useRealTimers());

  it('counts whole calendar days', () => {
    expect(daysUntil('2026-11-06')).toBe(0);
    expect(daysUntil('2026-11-07')).toBe(1);
    expect(daysUntil('2026-11-03')).toBe(-3);
    expect(daysUntil('2026-12-06')).toBe(30);
  });
});

describe('useFormat', () => {
  afterEach(async () => {
    await act(() => i18n.changeLanguage('en'));
  });

  it('formats money and dates for English', () => {
    const { result } = renderHook(() => useFormat());
    expect(result.current.money(10)).toBe('$10.00');
    expect(result.current.currencySymbol('EUR')).toBe('€');
    expect(result.current.date('2026-12-06')).toBe('Dec 6, 2026');
    expect(result.current.date(null)).toBe('—');
  });

  it('follows the UI language', async () => {
    const { result } = renderHook(() => useFormat());
    await act(() => i18n.changeLanguage('ru'));
    expect(result.current.money(10).replace(/\s/g, ' ')).toBe('10,00 $');
    expect(result.current.date('2026-12-06')).toBe('6 дек. 2026 г.');
  });

  it('falls back for unknown currency codes', () => {
    const { result } = renderHook(() => useFormat());
    expect(result.current.money(5, 'NOT_A_CURRENCY')).toBe('5.00 NOT_A_CURRENCY');
  });
});
