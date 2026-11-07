import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pencil, Plus, Trash2, Users } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { ChallengeDto, ChallengeParticipantDto } from '../../api/types';
import type { BookCategory } from '../types';
import { errorMessage } from '../utils/apiErrors';
import { useChallengeText } from '../utils/challenges';
import { useFormat } from '../utils/format';
import { getCategoryTranslation } from '../utils/translations';
import { useConfirm } from './ConfirmDialog';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';

const CATEGORIES: BookCategory[] = ['fiction', 'non-fiction', 'children', 'young-adult', 'science', 'history', 'biography'];
const SELECT = 'w-full border border-border rounded-md px-2 py-1.5 text-sm bg-background';

interface Draft {
  id?: string;
  nameEn: string;
  nameRu: string;
  descriptionEn: string;
  descriptionRu: string;
  startsOn: string;
  endsOn: string;
  goal: string;
  category: string;
}

const today = () => new Date().toISOString().slice(0, 10);
const empty = (): Draft => ({
  nameEn: '', nameRu: '', descriptionEn: '', descriptionRu: '', startsOn: today(), endsOn: today(), goal: '5', category: '',
});
const draftOf = (c: ChallengeDto): Draft => ({
  id: c.id,
  nameEn: c.name_en,
  nameRu: c.name_ru ?? '',
  descriptionEn: c.description_en,
  descriptionRu: c.description_ru ?? '',
  startsOn: c.starts_on,
  endsOn: c.ends_on,
  goal: String(c.goal),
  category: c.category ?? '',
});

/** Admin: reading challenges (goal, dates, optional category), who takes part and how far. */
export function ChallengesTab() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const textOf = useChallengeText();
  const { confirm, confirmDialog } = useConfirm();
  const [challenges, setChallenges] = useState<ChallengeDto[] | null>(null);
  const [draft, setDraft] = useState<Draft>(empty);
  const [saving, setSaving] = useState(false);
  const [people, setPeople] = useState<{ id: string; list: ChallengeParticipantDto[] } | null>(null);

  const load = useCallback(async () => {
    setChallenges(await adminApi.listChallenges().catch(() => []));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    const body = {
      name_en: draft.nameEn,
      name_ru: draft.nameRu.trim() || null,
      description_en: draft.descriptionEn,
      description_ru: draft.descriptionRu.trim() || null,
      starts_on: draft.startsOn,
      ends_on: draft.endsOn,
      goal: Number(draft.goal),
      category: (draft.category || null) as BookCategory | null,
    };
    const result = await runAction(() =>
      draft.id ? adminApi.updateChallenge(draft.id, body) : adminApi.createChallenge(body),
    );
    setSaving(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    toast.success(draft.id ? t('challenges.saved') : t('challenges.created'));
    setDraft(empty());
    await load();
  };

  const remove = async (challenge: ChallengeDto) => {
    const ok = await confirm({
      title: t('challenges.deleteTitle', { name: textOf(challenge).name }),
      description: t('challenges.deleteDesc'),
      confirmLabel: t('challenges.delete'),
      destructive: true,
    });
    if (!ok) return;
    const result = await runAction(() => adminApi.deleteChallenge(challenge.id));
    if (result.ok) await load();
    else toast.error(errorMessage(t, result.error));
  };

  const showPeople = async (challenge: ChallengeDto) => {
    if (people?.id === challenge.id) {
      setPeople(null);
      return;
    }
    const list = await adminApi.challengeParticipants(challenge.id).catch(() => []);
    setPeople({ id: challenge.id, list });
  };

  const field = (key: keyof Draft) => ({
    value: draft[key] ?? '',
    onChange: (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [key]: e.target.value })),
  });

  return (
    <div className="space-y-6">
      <form
        className="grid gap-4 sm:grid-cols-2 rounded-lg border border-border p-4"
        aria-label={draft.id ? t('challenges.editTitle') : t('challenges.newTitle')}
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <h2 className="sm:col-span-2 text-lg">{draft.id ? t('challenges.editTitle') : t('challenges.newTitle')}</h2>
        <div className="space-y-2">
          <Label htmlFor="challenge-name-en">{t('challenges.nameEn')}</Label>
          <Input id="challenge-name-en" required maxLength={200} {...field('nameEn')} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="challenge-name-ru">{t('challenges.nameRu')}</Label>
          <Input id="challenge-name-ru" maxLength={200} {...field('nameRu')} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="challenge-desc-en">{t('challenges.descriptionEn')}</Label>
          <Textarea id="challenge-desc-en" rows={2} maxLength={5000} {...field('descriptionEn')} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="challenge-desc-ru">{t('challenges.descriptionRu')}</Label>
          <Textarea id="challenge-desc-ru" rows={2} maxLength={5000} {...field('descriptionRu')} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="challenge-starts">{t('challenges.startsOn')}</Label>
            <Input id="challenge-starts" type="date" required {...field('startsOn')} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="challenge-ends">{t('challenges.endsOn')}</Label>
            <Input id="challenge-ends" type="date" required min={draft.startsOn} {...field('endsOn')} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="challenge-goal">{t('challenges.goalLabel')}</Label>
            <Input id="challenge-goal" type="number" min={1} max={100} required {...field('goal')} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="challenge-category">{t('challenges.categoryLabel')}</Label>
            <select id="challenge-category" className={SELECT} {...field('category')}>
              <option value="">{t('challenges.anyBook')}</option>
              {CATEGORIES.map((category) => (
                <option key={category} value={category}>{getCategoryTranslation(t, category)}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="sm:col-span-2 flex gap-2">
          <Button type="submit" disabled={saving || !draft.nameEn.trim()}>
            {draft.id ? <Pencil className="w-4 h-4 mr-1" aria-hidden="true" /> : <Plus className="w-4 h-4 mr-1" aria-hidden="true" />}
            {draft.id ? t('challenges.save') : t('challenges.create')}
          </Button>
          {draft.id && (
            <Button type="button" variant="ghost" onClick={() => setDraft(empty())}>{t('common.cancel')}</Button>
          )}
        </div>
      </form>

      {challenges === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : challenges.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('challenges.none')}</p>
      ) : (
        <ul className="space-y-3">
          {challenges.map((challenge) => (
            <li key={challenge.id} className="rounded-lg border border-border p-3 space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{textOf(challenge).name}</p>
                  <p className="text-sm text-muted-foreground">
                    {fmt.date(challenge.starts_on)} – {fmt.date(challenge.ends_on)} ·{' '}
                    {challenge.category
                      ? t('challenges.goalInCategory', { count: challenge.goal, category: getCategoryTranslation(t, challenge.category) })
                      : t('challenges.goal', { count: challenge.goal })}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{t('challenges.counts', { joined: challenge.participants, done: challenge.completed })}</Badge>
                  <Button size="sm" variant="outline" onClick={() => showPeople(challenge)} aria-expanded={people?.id === challenge.id}>
                    <Users className="w-4 h-4 mr-1" aria-hidden="true" />
                    {t('challenges.participants')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDraft(draftOf(challenge))} aria-label={t('challenges.editNamed', { name: textOf(challenge).name })}>
                    <Pencil className="w-4 h-4" aria-hidden="true" />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(challenge)} aria-label={t('challenges.deleteNamed', { name: textOf(challenge).name })}>
                    <Trash2 className="w-4 h-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
              {people?.id === challenge.id && (
                people.list.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t('challenges.nobody')}</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th className="font-normal py-1">{t('challenges.reader')}</th>
                        <th className="font-normal py-1">{t('challenges.read')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {people.list.map((person, index) => (
                        <tr key={`${person.name}-${index}`} className="border-t border-border">
                          <td className="py-1">
                            {person.name}
                            {person.parent_name && <span className="text-muted-foreground"> ({t('challenges.childOf', { name: person.parent_name })})</span>}
                          </td>
                          <td className="py-1 tabular-nums">
                            {person.read} / {challenge.goal} {person.completed && <Badge className="ml-1">{t('challenges.done')}</Badge>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              )}
            </li>
          ))}
        </ul>
      )}
      {confirmDialog}
    </div>
  );
}
