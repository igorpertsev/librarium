import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BookOpen,
  CalendarCheck,
  Compass,
  Crown,
  Languages,
  Layers,
  Library,
  Trophy,
  X,
  type LucideIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import { useReadingLog } from '../contexts/ReadingLogContext';
import { errorMessage } from '../utils/apiErrors';
import { useBookText } from '../utils/bookText';
import { coverOfSize } from '../utils/covers';
import { useFormat } from '../utils/format';
import { FinishedButton } from './FinishedButton';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { cn } from './ui/utils';

const BADGE_ICONS: Record<string, LucideIcon> = {
  first_book: BookOpen,
  five_books: Library,
  ten_books: Trophy,
  twenty_five_books: Crown,
  explorer: Compass,
  two_languages: Languages,
  series_finisher: Layers,
  three_months: CalendarCheck,
};
const SHOWN = 8;

/** Profile: books the reader has finished, badges, and borrowed books to log. */
export function ReadingLogCard() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const textOf = useBookText();
  const { log, unmark } = useReadingLog();
  const [showAll, setShowAll] = useState(false);

  if (!log) return null;
  const earned = log.badges.filter((badge) => badge.earned).length;
  const entries = showAll ? log.entries : log.entries.slice(0, SHOWN);

  return (
    <Card data-testid="reading-log">
      <CardHeader>
        <CardTitle>{t('readingLog.title')}</CardTitle>
        <CardDescription>
          {t('readingLog.summary', { year: log.thisYear, total: log.total, badges: t('readingLog.badgeCount', { count: earned }) })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <ul className="grid grid-cols-2 sm:grid-cols-4 gap-3" aria-label={t('readingLog.badges')}>
          {log.badges.map((badge) => {
            const Icon = BADGE_ICONS[badge.key] ?? Trophy;
            return (
              <li
                key={badge.key}
                className={cn(
                  'flex flex-col items-center gap-1 rounded-lg border p-3 text-center',
                  badge.earned ? 'border-primary bg-primary/10' : 'border-dashed border-border',
                )}
              >
                <Icon
                  className={cn('w-7 h-7', badge.earned ? 'text-primary' : 'text-muted-foreground')}
                  aria-hidden="true"
                />
                <span className="text-sm font-medium">{t(`readingLog.badge.${badge.key}.name`)}</span>
                <span className="text-xs text-muted-foreground">{t(`readingLog.badge.${badge.key}.hint`)}</span>
                <span className="text-xs tabular-nums">
                  {badge.earned ? t('readingLog.earned') : t('readingLog.progress', { progress: badge.progress, goal: badge.goal })}
                </span>
              </li>
            );
          })}
        </ul>

        {log.toLog.length > 0 && (
          <section aria-labelledby="to-log-title" className="space-y-2">
            <h3 id="to-log-title" className="text-sm font-medium">{t('readingLog.toLog')}</h3>
            <ul className="space-y-2">
              {log.toLog.map((book) => {
                const text = textOf(book);
                return (
                  <li key={book.id} className="flex items-center gap-3">
                    <span className="flex-1 min-w-0 truncate text-sm">{text.title}</span>
                    <FinishedButton bookId={book.id} groupId={book.groupId} title={text.title} size="sm" />
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {log.entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('readingLog.empty')}</p>
        ) : (
          <section aria-labelledby="finished-title" className="space-y-2">
            <h3 id="finished-title" className="text-sm font-medium">{t('readingLog.finishedBooks')}</h3>
            <ul className="space-y-2">
              {entries.map(({ book, finishedOn }) => {
                const text = textOf(book);
                return (
                  <li key={book.id} className="flex items-center gap-3">
                    <div className="w-8 h-11 flex-shrink-0 overflow-hidden rounded bg-muted">
                      <img src={coverOfSize(book.coverImage, 'S')} alt="" className="w-full h-full object-cover" loading="lazy" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-sm">{text.title}</p>
                      <p className="text-xs text-muted-foreground">{t('readingLog.finishedOn', { date: fmt.date(finishedOn) })}</p>
                    </div>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={t('readingLog.unmarkTitle', { title: text.title })}
                      onClick={async () => {
                        const result = await unmark(book.id);
                        if (result.ok) toast.success(t('readingLog.unmarked', { title: text.title }));
                        else toast.error(errorMessage(t, result.error));
                      }}
                    >
                      <X className="w-4 h-4" aria-hidden="true" />
                    </Button>
                  </li>
                );
              })}
            </ul>
            {log.entries.length > SHOWN && (
              <Button variant="ghost" size="sm" onClick={() => setShowAll((all) => !all)}>
                {showAll ? t('readingLog.showLess') : t('readingLog.showAll', { count: log.entries.length })}
              </Button>
            )}
          </section>
        )}
      </CardContent>
    </Card>
  );
}
