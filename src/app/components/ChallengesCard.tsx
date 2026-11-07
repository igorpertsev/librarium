import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Trophy } from 'lucide-react';
import { toast } from 'sonner';
import { challengesApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { ChallengeDto } from '../../api/types';
import { useFamily } from '../contexts/FamilyContext';
import { useReadingLog } from '../contexts/ReadingLogContext';
import { errorMessage } from '../utils/apiErrors';
import { useChallengeText } from '../utils/challenges';
import { useFormat } from '../utils/format';
import { getCategoryTranslation } from '../utils/translations';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Progress } from './ui/progress';

/** Profile: the library's reading challenges, with progress for the reader and each child. */
export function ChallengesCard() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const textOf = useChallengeText();
  const { children: kids } = useFamily();
  // Marking a book read changes the log: progress is reloaded then.
  const { log } = useReadingLog();
  const [challenges, setChallenges] = useState<ChallengeDto[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setChallenges(await challengesApi.list().catch(() => []));
  }, []);

  useEffect(() => {
    void load();
  }, [load, log]);

  if (!challenges || challenges.length === 0) return null;
  const profiles: { id: string | null; name: string }[] = [
    { id: null, name: t('readingLog.me') },
    ...kids.map((kid) => ({ id: kid.id, name: kid.name })),
  ];

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    const result = await runAction(action);
    setBusy(false);
    if (result.ok) await load();
    else toast.error(errorMessage(t, result.error));
  };

  return (
    <Card data-testid="challenges">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Trophy className="w-5 h-5" aria-hidden="true" />
          {t('challenges.title')}
        </CardTitle>
        <CardDescription>{t('challenges.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {challenges.map((challenge) => {
          const text = textOf(challenge);
          const started = new Date(challenge.starts_on) <= new Date();
          return (
            <section key={challenge.id} aria-labelledby={`challenge-${challenge.id}`} className="space-y-2">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 id={`challenge-${challenge.id}`} className="font-medium">{text.name}</h3>
                <span className="text-sm text-muted-foreground">
                  {fmt.date(challenge.starts_on)} – {fmt.date(challenge.ends_on)}
                </span>
              </div>
              <p className="text-sm">
                {challenge.category
                  ? t('challenges.goalInCategory', { count: challenge.goal, category: getCategoryTranslation(t, challenge.category) })
                  : t('challenges.goal', { count: challenge.goal })}
                {!started && ` · ${t('challenges.upcoming')}`}
              </p>
              {text.description && <p className="text-sm text-muted-foreground">{text.description}</p>}
              <ul className="space-y-2">
                {profiles.map((profile) => {
                  const entry = challenge.mine.find((p) => (p.child_id ?? null) === profile.id);
                  return (
                    <li key={profile.id ?? 'me'} className="flex flex-wrap items-center gap-3">
                      <span className="w-24 text-sm truncate">{profile.name}</span>
                      {entry ? (
                        <>
                          <Progress
                            value={Math.min(100, (entry.read / challenge.goal) * 100)}
                            className="h-2 flex-1 min-w-24"
                            aria-label={t('challenges.progressLabel', { name: profile.name, read: entry.read, goal: challenge.goal })}
                          />
                          <span className="text-sm tabular-nums">{entry.read} / {challenge.goal}</span>
                          {entry.completed && <Badge>{t('challenges.done')}</Badge>}
                          <Button variant="ghost" size="sm" disabled={busy} onClick={() => act(() => challengesApi.leave(challenge.id, profile.id))}>
                            {t('challenges.leave')}
                          </Button>
                        </>
                      ) : (
                        <Button variant="outline" size="sm" disabled={busy} onClick={() => act(() => challengesApi.join(challenge.id, profile.id))}>
                          {t('challenges.join')}
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
        <p className="text-xs text-muted-foreground">{t('challenges.howItCounts')}</p>
      </CardContent>
    </Card>
  );
}
