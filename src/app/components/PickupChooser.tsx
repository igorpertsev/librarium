import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MapPin } from 'lucide-react';
import { libraryApi } from '../../api/endpoints';
import type { PickupChoiceDto, PickupPointDto, PickupSlotDto } from '../../api/types';
import { cn } from './ui/utils';
import { useFormat } from '../utils/format';
import { useHoursText } from '../utils/pickup';
import { useLibraryRules } from '../utils/useLibraryRules';
import { Label } from './ui/label';
import { RadioGroup, RadioGroupItem } from './ui/radio-group';

interface Props {
  points: PickupPointDto[];
  value: PickupChoiceDto | null;
  onChange: (choice: PickupChoiceDto | null) => void;
  /** Bump to load the slots again (after a slot filled up). */
  reloadKey?: number;
}

/** Checkout: where (pickup point) and when (one of its free slots) to collect the order. */
export function PickupChooser({ points, value, onChange, reloadKey = 0 }: Props) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const rules = useLibraryRules();
  const hoursText = useHoursText();
  const timeZone = rules?.timezone ?? 'UTC';
  const zone = useMemo(() => fmt.zoned(timeZone), [fmt, timeZone]);
  const [pointId, setPointId] = useState<string | null>(points.length === 1 ? points[0].id : null);
  const [slots, setSlots] = useState<PickupSlotDto[] | null>(null);
  const [day, setDay] = useState<string | null>(null);

  useEffect(() => {
    if (!pointId) return;
    let active = true;
    setSlots(null);
    libraryApi.pickupSlots(pointId).then(
      (list) => active && setSlots(list),
      () => active && setSlots([]),
    );
    return () => {
      active = false;
    };
  }, [pointId, reloadKey]);

  const days = useMemo(() => {
    const grouped = new Map<string, PickupSlotDto[]>();
    for (const slot of slots ?? []) {
      const key = zone.dayKey(slot.starts_at);
      grouped.set(key, [...(grouped.get(key) ?? []), slot]);
    }
    return [...grouped.entries()].filter(([, list]) => list.some((s) => s.left !== 0));
  }, [slots, zone]);
  const shownDay = day && days.some(([key]) => key === day) ? day : (days[0]?.[0] ?? null);
  const daySlots = days.find(([key]) => key === shownDay)?.[1] ?? [];

  const choosePoint = (id: string) => {
    setPointId(id);
    setDay(null);
    onChange(null);
  };

  return (
    <div className="space-y-3" data-testid="pickup-chooser">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium mb-1">{t('pickup.where')}</legend>
        <RadioGroup value={pointId ?? ''} onValueChange={choosePoint} className="gap-2">
          {points.map((point) => (
            <Label
              key={point.id}
              htmlFor={`pickup-${point.id}`}
              className={cn(
                'flex items-start gap-3 rounded-md border border-border p-3 cursor-pointer font-normal',
                pointId === point.id && 'border-primary bg-primary/5',
              )}
            >
              <RadioGroupItem id={`pickup-${point.id}`} value={point.id} className="mt-0.5" />
              <span className="space-y-0.5 min-w-0">
                <span className="flex items-center gap-1 font-medium">
                  <MapPin className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                  {point.name}
                </span>
                <span className="block text-sm text-muted-foreground">{point.address}</span>
                {point.hours.length > 0 && (
                  <span className="block text-xs text-muted-foreground">{hoursText(point.hours)}</span>
                )}
                {point.notes && <span className="block text-xs text-muted-foreground">{point.notes}</span>}
              </span>
            </Label>
          ))}
        </RadioGroup>
      </fieldset>

      {pointId && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium mb-1">{t('pickup.when')}</legend>
          {slots === null ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : days.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('pickup.noSlots')}</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('pickup.day')}>
                {days.map(([key, list]) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={key === shownDay}
                    onClick={() => setDay(key)}
                    className={cn(
                      'rounded-md border px-2.5 py-1 text-sm',
                      key === shownDay ? 'border-primary bg-primary text-primary-foreground' : 'border-border hover:bg-muted',
                    )}
                  >
                    {zone.day(list[0].starts_at)}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('pickup.time')}>
                {daySlots.map((slot) => {
                  const full = slot.left === 0;
                  const chosen = value?.pickup_at === slot.starts_at && value.pickup_point_id === pointId;
                  return (
                    <button
                      key={slot.starts_at}
                      type="button"
                      disabled={full}
                      aria-pressed={chosen}
                      title={full ? t('pickup.full') : undefined}
                      onClick={() => onChange({ pickup_point_id: pointId, pickup_at: slot.starts_at })}
                      className={cn(
                        'rounded-md border px-2.5 py-1 text-sm tabular-nums',
                        chosen ? 'border-primary bg-primary text-primary-foreground' : 'border-border hover:bg-muted',
                        full && 'opacity-50 line-through cursor-not-allowed hover:bg-transparent',
                      )}
                    >
                      {zone.time(slot.starts_at)}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </fieldset>
      )}
    </div>
  );
}
