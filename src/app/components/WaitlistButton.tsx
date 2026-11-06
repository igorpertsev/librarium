import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell, BellRing } from 'lucide-react';
import { toast } from 'sonner';
import { useWaitlist } from '../contexts/WaitlistContext';
import { errorMessage } from '../utils/apiErrors';
import { Button } from './ui/button';

/** "Email me when it is back" toggle for a book that cannot be ordered now. */
export function WaitlistButton({
  bookId,
  groupId,
  title,
  withLabel = false,
}: {
  bookId: string;
  groupId?: string;
  title: string;
  withLabel?: boolean;
}) {
  const { t } = useTranslation();
  const { isWaiting, join, leave } = useWaitlist();
  const [busy, setBusy] = useState(false);
  const waiting = isWaiting({ id: bookId, groupId });

  const toggle = async () => {
    setBusy(true);
    const result = waiting ? await leave(bookId) : await join(bookId);
    setBusy(false);
    if (!result.ok) toast.error(errorMessage(t, result.error));
    else toast.success(waiting ? t('waitlist.left', { title }) : t('waitlist.joined', { title }));
  };

  const label = waiting ? t('waitlist.stop', { title }) : t('waitlist.notifyMe', { title });
  const Icon = waiting ? BellRing : Bell;
  return (
    <Button
      type="button"
      variant={waiting ? 'secondary' : 'outline'}
      size={withLabel ? 'default' : 'icon'}
      onClick={toggle}
      disabled={busy}
      aria-pressed={waiting}
      aria-label={withLabel ? undefined : label}
      title={label}
      className={withLabel ? undefined : 'shrink-0'}
    >
      <Icon className={withLabel ? 'w-4 h-4 mr-2' : 'w-4 h-4'} aria-hidden="true" />
      {withLabel && (waiting ? t('waitlist.waiting') : t('waitlist.notifyMeShort'))}
    </Button>
  );
}
