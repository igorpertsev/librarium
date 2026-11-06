/**
 * Format an API calendar date ("2026-12-06") for display in the UI language.
 * Parsed as a local date: `new Date("2026-12-06")` would mean UTC midnight and show the
 * previous day west of UTC.
 */
export function formatCalendarDate(value: string, language: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(language.startsWith('ru') ? 'ru-RU' : 'en-US', { dateStyle: 'medium' }).format(date);
}
