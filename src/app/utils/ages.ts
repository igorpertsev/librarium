/** The youngest age a book is labelled for: the first number of its age range ("8+", "6-10",
 * "12 лет" → 8, 6, 12); null for books without one (they suit everyone). Same rule as the
 * backend's ``for_age`` filter. */
export function minAge(ageRange: string | null | undefined): number | null {
  const match = /^\s*(\d{1,2})/.exec(ageRange ?? '');
  return match ? Number(match[1]) : null;
}

/** A child's age from the birth year (the birthday is not known, so it may be one too high). */
export function childAge(birthYear: number | null | undefined, today: Date = new Date()): number | null {
  if (!birthYear) return null;
  const age = today.getFullYear() - birthYear;
  return age >= 0 && age <= 18 ? age : null;
}

/** The ``for_age`` address-bar value, when it is a usable age. */
export function parseForAge(value: string | null): number | null {
  if (value === null || !/^\d{1,2}$/.test(value)) return null;
  const age = Number(value);
  return age <= 18 ? age : null;
}
