import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { MapPin } from 'lucide-react';
import type { Order } from '../types';
import { useFormat } from '../utils/format';
import { useLibraryRules } from '../utils/useLibraryRules';

/** "Pick up: Main hall, 1 Library Road · Mon, 9 Nov, 10:00" (in the library's time zone). */
export function PickupLine({ order, className }: { order: Order; className?: string }) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const timeZone = useLibraryRules()?.timezone ?? 'UTC';
  const zone = useMemo(() => fmt.zoned(timeZone), [fmt, timeZone]);
  if (!order.pickup) return null;
  return (
    <p className={className ?? 'flex items-start gap-1 text-sm text-muted-foreground'}>
      <MapPin className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
      <span>
        {t('pickup.line', { place: `${order.pickup.name}, ${order.pickup.address}` })}
        {order.pickupAt && ` · ${zone.dateTime(order.pickupAt)}`}
      </span>
    </p>
  );
}
