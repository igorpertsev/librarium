import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BookCheck, BookOpen } from 'lucide-react';
import { toast } from 'sonner';
import { useReadingLog } from '../contexts/ReadingLogContext';
import { useFamily } from '../contexts/FamilyContext';
import { errorMessage } from '../utils/apiErrors';
import { Button } from './ui/button';

/** "I've read it" toggle for the reading log (badges count these). */
export function FinishedButton({
  bookId,
  groupId,
  title,
  size = 'default',
}: {
  bookId: string;
  groupId?: string;
  title: string;
  size?: 'default' | 'sm';
}) {
  const { t } = useTranslation();
  const { isFinished, markFinished, unmark, profile } = useReadingLog();
  const { children: kids } = useFamily();
  const child = kids.find((kid) => kid.id === profile);
  const [busy, setBusy] = useState(false);
  const finished = isFinished({ id: bookId, groupId });

  const toggle = async () => {
    setBusy(true);
    const result = finished ? await unmark(bookId) : await markFinished(bookId);
    setBusy(false);
    if (!result.ok) toast.error(errorMessage(t, result.error));
    else toast.success(finished ? t('readingLog.unmarked', { title }) : t('readingLog.marked', { title }));
  };

  const Icon = finished ? BookCheck : BookOpen;
  return (
    <Button
      type="button"
      size={size}
      variant={finished ? 'secondary' : 'outline'}
      onClick={toggle}
      disabled={busy}
      aria-pressed={finished}
      title={finished ? t('readingLog.unmarkTitle', { title }) : t('readingLog.markTitle', { title })}
    >
      <Icon className="w-4 h-4 mr-2" aria-hidden="true" />
      {child
        ? finished
          ? t('readingLog.finishedBy', { name: child.name })
          : t('readingLog.markFor', { name: child.name })
        : finished
          ? t('readingLog.finished')
          : t('readingLog.markShort')}
    </Button>
  );
}
