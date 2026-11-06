import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

/** UI language → formatting locale. */
const LOCALE_BY_LANGUAGE: Record<string, string> = { en: 'en-US', ru: 'ru-RU' };
const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Parse a date from the API. Date-only values ("2026-12-06") are calendar days in the
 * user's time zone; `new Date("2026-12-06")` would read them as UTC midnight and show the
 * previous day west of UTC.
 */
export function parseDate(value: string | Date): Date | null {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Whole calendar days from today until the date (0 = today, negative = in the past). */
export function daysUntil(value: string | Date): number {
  const date = parseDate(value);
  if (!date) return 0;
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  return Math.round((target.getTime() - start.getTime()) / DAY_MS);
}

function zonedFormat(locale: string, timeZone: string) {
  const make = (options: Intl.DateTimeFormatOptions, inLocale = locale) => {
    try {
      return new Intl.DateTimeFormat(inLocale, { ...options, timeZone });
    } catch {
      return new Intl.DateTimeFormat(inLocale, options); // unknown time zone
    }
  };
  const day = make({ weekday: 'short', day: 'numeric', month: 'short' });
  const time = make({ hour: 'numeric', minute: '2-digit' });
  const key = make({ year: 'numeric', month: '2-digit', day: '2-digit' }, 'en-CA');
  const at = (value: string) => new Date(value);
  return {
    /** "Mon, 9 Nov" */
    day: (value: string) => day.format(at(value)),
    /** "10:00" */
    time: (value: string) => time.format(at(value)),
    /** "2026-11-09": groups moments by calendar day in that zone. */
    dayKey: (value: string) => key.format(at(value)),
    /** "Mon, 9 Nov, 10:00" */
    dateTime: (value: string) => `${day.format(at(value))}, ${time.format(at(value))}`,
  };
}

/** Money and date formatters for the current UI language. */
export function useFormat() {
  const { i18n } = useTranslation();
  const language = (i18n.language ?? 'en').split('-')[0];
  const locale = LOCALE_BY_LANGUAGE[language] ?? 'en-US';

  return useMemo(() => {
    const dateFormat = new Intl.DateTimeFormat(locale, { dateStyle: 'medium' });
    const dateTimeFormat = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
    const moneyFormat = (currency: string, extra: Intl.NumberFormatOptions = {}) => {
      try {
        return new Intl.NumberFormat(locale, { style: 'currency', currency, ...extra });
      } catch {
        return null; // unknown currency code
      }
    };
    return {
      locale,
      money: (amount: number, currency = 'USD') =>
        moneyFormat(currency)?.format(amount) ?? `${amount.toFixed(2)} ${currency}`,
      currencySymbol: (currency = 'USD') =>
        moneyFormat(currency, { currencyDisplay: 'narrowSymbol' })
          ?.formatToParts(0)
          .find((part) => part.type === 'currency')?.value ?? currency,
      date: (value: string | Date | null | undefined) => {
        const date = value ? parseDate(value) : null;
        return date ? dateFormat.format(date) : '—';
      },
      /** Formatters for moments in another time zone (the library's), e.g. pickup slots. */
      zoned: (timeZone: string) => zonedFormat(locale, timeZone),
      /** A moment (ISO timestamp) in the reader's time zone, e.g. "8 Nov 2026, 14:30". */
      dateTime: (value: string | Date) => dateTimeFormat.format(typeof value === 'string' ? new Date(value) : value),
    };
  }, [locale]);
}
