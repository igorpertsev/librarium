import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MapPin, Pencil, Plus, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { OpeningHoursDto, PickupPointDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { useHoursText } from '../utils/pickup';
import { invalidateLibraryRules } from '../utils/useLibraryRules';
import { useConfirm } from './ConfirmDialog';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Textarea } from './ui/textarea';

const SLOT_LENGTHS = [15, 20, 30, 45, 60, 90, 120];
const SELECT = 'border border-border rounded-md px-2 py-1.5 text-sm bg-background';

interface Draft {
  id?: string;
  name: string;
  address: string;
  notes: string;
  hours: OpeningHoursDto[];
  slotMinutes: number;
  capacity: string;
  active: boolean;
}

const WEEKDAYS_10_TO_6: OpeningHoursDto[] = [0, 1, 2, 3, 4].map((weekday) => ({
  weekday,
  opens: '10:00',
  closes: '18:00',
}));

const emptyDraft = (): Draft => ({
  name: '',
  address: '',
  notes: '',
  hours: WEEKDAYS_10_TO_6,
  slotMinutes: 60,
  capacity: '',
  active: true,
});

const draftOf = (point: PickupPointDto): Draft => ({
  id: point.id,
  name: point.name,
  address: point.address,
  notes: point.notes ?? '',
  hours: point.hours.map((h) => ({ ...h, opens: h.opens.slice(0, 5), closes: h.closes.slice(0, 5) })),
  slotMinutes: point.slot_minutes,
  capacity: point.slot_capacity == null ? '' : String(point.slot_capacity),
  active: point.active,
});

function useTimeZones(): string[] {
  return useMemo(() => {
    try {
      return Intl.supportedValuesOf('timeZone');
    } catch {
      return [];
    }
  }, []);
}

/** Admin: where readers collect orders, their weekly hours and pickup slots. */
export function PickupPointsTab() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const hoursText = useHoursText();
  const timeZones = useTimeZones();
  const { confirm, confirmDialog } = useConfirm();
  const [points, setPoints] = useState<PickupPointDto[] | null>(null);
  const [timeZone, setTimeZone] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const weekdayNames = useMemo(() => {
    const format = new Intl.DateTimeFormat(fmt.locale, { weekday: 'long', timeZone: 'UTC' });
    return [0, 1, 2, 3, 4, 5, 6].map((day) => format.format(new Date(Date.UTC(2024, 0, 1 + day))));
  }, [fmt.locale]);

  const load = useCallback(async () => {
    setPoints(await adminApi.listPickupPoints().catch(() => []));
  }, []);

  useEffect(() => {
    void load();
    adminApi.getSettings().then(
      (settings) => setTimeZone((typed) => typed || settings.timezone),
      () => undefined,
    );
  }, [load]);

  const act = async (action: () => Promise<unknown>, done: string): Promise<boolean> => {
    const result = await runAction(action);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return false;
    }
    toast.success(done);
    await load();
    return true;
  };

  const saveTimeZone = async () => {
    const result = await runAction(() => adminApi.updateSettings({ timezone: timeZone }));
    if (result.ok) {
      invalidateLibraryRules();
      toast.success(t('pickup.timeZoneSaved'));
    } else {
      toast.error(errorMessage(t, result.error));
    }
  };

  const saveDraft = async () => {
    if (!draft) return;
    setSaving(true);
    const body = {
      name: draft.name,
      address: draft.address,
      notes: draft.notes || null,
      hours: draft.hours,
      slot_minutes: draft.slotMinutes,
      slot_capacity: draft.capacity ? Number.parseInt(draft.capacity, 10) : null,
      active: draft.active,
    };
    const saved = await act(
      () => (draft.id ? adminApi.updatePickupPoint(draft.id, body) : adminApi.createPickupPoint(body)),
      t('pickup.saved'),
    );
    setSaving(false);
    if (saved) setFormOpen(false);
  };

  const edit = (next: Draft) => {
    setDraft(next);
    setFormOpen(true);
  };

  const remove = async (point: PickupPointDto) => {
    const confirmed = await confirm({
      title: t('pickup.deleteTitle'),
      description: t('pickup.deleteDesc', { name: point.name }),
      confirmLabel: t('confirm.remove'),
      destructive: true,
    });
    if (confirmed) await act(() => adminApi.deletePickupPoint(point.id), t('pickup.deleted'));
  };

  const setHours = (index: number, change: Partial<OpeningHoursDto>) =>
    draft && setDraft({ ...draft, hours: draft.hours.map((h, i) => (i === index ? { ...h, ...change } : h)) });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg">{t('pickup.title')}</h2>
        <p className="text-sm text-muted-foreground">{t('pickup.description')}</p>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-2">
          <Label htmlFor="libraryTimeZone">{t('pickup.timeZone')}</Label>
          <Input
            id="libraryTimeZone"
            list="time-zones"
            value={timeZone}
            onChange={(e) => setTimeZone(e.target.value)}
            className="w-64"
          />
          <datalist id="time-zones">
            {timeZones.map((zone) => (
              <option key={zone} value={zone} />
            ))}
          </datalist>
        </div>
        <Button variant="outline" onClick={saveTimeZone} disabled={!timeZone}>
          {t('pickup.saveTimeZone')}
        </Button>
        <Button className="ml-auto" onClick={() => edit(emptyDraft())}>
          <Plus className="w-4 h-4 mr-1" aria-hidden="true" />
          {t('pickup.add')}
        </Button>
      </div>

      {points === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : points.length === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">{t('pickup.empty')}</p>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {points.map((point) => (
            <li key={point.id} className="rounded-lg border border-border p-4 space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium flex items-center gap-1">
                    <MapPin className="w-4 h-4 shrink-0" aria-hidden="true" />
                    {point.name}
                  </p>
                  <p className="text-sm text-muted-foreground">{point.address}</p>
                </div>
                <Badge variant={point.active ? 'default' : 'outline'}>
                  {point.active ? t('pickup.active') : t('pickup.inactive')}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">{point.hours.length ? hoursText(point.hours) : t('pickup.noHours')}</p>
              <p className="text-xs text-muted-foreground">
                {t('pickup.slotSummary', { minutes: point.slot_minutes })}
                {' · '}
                {point.slot_capacity == null ? t('pickup.noLimit') : t('pickup.perSlot', { count: point.slot_capacity })}
              </p>
              {point.notes && <p className="text-xs text-muted-foreground">{point.notes}</p>}
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="outline" onClick={() => edit(draftOf(point))}>
                  <Pencil className="w-3.5 h-3.5 mr-1" aria-hidden="true" />
                  {t('pickup.edit')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    act(
                      () => adminApi.updatePickupPoint(point.id, { active: !point.active }),
                      point.active ? t('pickup.switchedOff') : t('pickup.switchedOn'),
                    )
                  }
                >
                  {point.active ? t('pickup.switchOff') : t('pickup.switchOn')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive dark:text-red-400"
                  onClick={() => remove(point)}
                  aria-label={t('pickup.deleteNamed', { name: point.name })}
                >
                  <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{draft?.id ? t('pickup.editTitle') : t('pickup.addTitle')}</DialogTitle>
            <DialogDescription>{t('pickup.formHint')}</DialogDescription>
          </DialogHeader>
          {draft && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="pickupName">{t('pickup.name')}</Label>
                <Input id="pickupName" value={draft.name} maxLength={120} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pickupAddress">{t('pickup.address')}</Label>
                <Input id="pickupAddress" value={draft.address} maxLength={255} onChange={(e) => setDraft({ ...draft, address: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pickupNotes">{t('pickup.notes')}</Label>
                <Textarea id="pickupNotes" rows={2} maxLength={500} value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="pickupSlot">{t('pickup.slotLength')}</Label>
                  <select
                    id="pickupSlot"
                    className={`${SELECT} w-full`}
                    value={draft.slotMinutes}
                    onChange={(e) => setDraft({ ...draft, slotMinutes: Number(e.target.value) })}
                  >
                    {SLOT_LENGTHS.map((minutes) => (
                      <option key={minutes} value={minutes}>
                        {t('pickup.minutes', { count: minutes })}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="pickupCapacity">{t('pickup.capacity')}</Label>
                  <Input
                    id="pickupCapacity"
                    type="number"
                    min="1"
                    max="100"
                    placeholder={t('pickup.noLimit')}
                    value={draft.capacity}
                    onChange={(e) => setDraft({ ...draft, capacity: e.target.value })}
                  />
                </div>
              </div>
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">{t('pickup.hours')}</legend>
                {draft.hours.map((period, index) => (
                  // Rows have no identity of their own; the index is stable while editing.
                  <div key={index} className="flex flex-wrap items-center gap-2">
                    <select
                      aria-label={t('pickup.weekday')}
                      className={SELECT}
                      value={period.weekday}
                      onChange={(e) => setHours(index, { weekday: Number(e.target.value) })}
                    >
                      {weekdayNames.map((name, day) => (
                        <option key={name} value={day}>
                          {name}
                        </option>
                      ))}
                    </select>
                    <Input
                      type="time"
                      aria-label={t('pickup.opens')}
                      className="w-28"
                      value={period.opens}
                      onChange={(e) => setHours(index, { opens: e.target.value })}
                    />
                    <span aria-hidden="true">–</span>
                    <Input
                      type="time"
                      aria-label={t('pickup.closes')}
                      className="w-28"
                      value={period.closes}
                      onChange={(e) => setHours(index, { closes: e.target.value })}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={t('pickup.removeHours')}
                      onClick={() => setDraft({ ...draft, hours: draft.hours.filter((_, i) => i !== index) })}
                    >
                      <X className="w-4 h-4" aria-hidden="true" />
                    </Button>
                  </div>
                ))}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setDraft({ ...draft, hours: [...draft.hours, { weekday: 5, opens: '10:00', closes: '14:00' }] })
                  }
                >
                  <Plus className="w-3.5 h-3.5 mr-1" aria-hidden="true" />
                  {t('pickup.addHours')}
                </Button>
              </fieldset>
              <div className="flex items-center gap-2">
                <Switch id="pickupActive" checked={draft.active} onCheckedChange={(active) => setDraft({ ...draft, active })} />
                <Label htmlFor="pickupActive">{t('pickup.activeLabel')}</Label>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={saveDraft} disabled={saving || !draft?.name.trim() || !draft.address.trim()}>
              {t('pickup.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {confirmDialog}
    </div>
  );
}
