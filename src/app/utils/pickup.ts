import { useEffect, useMemo, useState } from 'react';
import { libraryApi } from '../../api/endpoints';
import type { OpeningHoursDto, PickupPointDto } from '../../api/types';
import { useFormat } from './format';

/** Active pickup points (empty: orders need none; null while loading). */
export function usePickupPoints(): PickupPointDto[] | null {
  const [points, setPoints] = useState<PickupPointDto[] | null>(null);
  useEffect(() => {
    let active = true;
    libraryApi.pickupPoints().then(
      (list) => active && setPoints(list),
      () => active && setPoints([]), // the server still checks when the order is placed
    );
    return () => {
      active = false;
    };
  }, []);
  return points;
}

/** "Mon 10:00–18:00 · Tue 10:00–14:00" in the UI language. */
export function useHoursText(): (hours: OpeningHoursDto[]) => string {
  const fmt = useFormat();
  return useMemo(() => {
    // 1 January 2024 was a Monday, like weekday 0.
    const weekday = new Intl.DateTimeFormat(fmt.locale, { weekday: 'short', timeZone: 'UTC' });
    const name = (day: number) => weekday.format(new Date(Date.UTC(2024, 0, 1 + day)));
    const hm = (value: string) => value.slice(0, 5);
    return (hours) =>
      hours.map((h) => `${name(h.weekday)} ${hm(h.opens)}–${hm(h.closes)}`).join(' · ');
  }, [fmt.locale]);
}

