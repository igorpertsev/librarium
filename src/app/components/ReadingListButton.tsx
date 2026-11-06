import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bookmark, BookmarkCheck } from 'lucide-react';
import { toast } from 'sonner';
import { useReadingList } from '../contexts/ReadingListContext';
import { errorMessage } from '../utils/apiErrors';
import { Button } from './ui/button';

/** "Want to read" toggle: keeps a title for later without putting it in the cart. */
export function ReadingListButton({
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
  const { has, add, remove } = useReadingList();
  const [busy, setBusy] = useState(false);
  const saved = has({ id: bookId, groupId });

  const toggle = async () => {
    setBusy(true);
    const result = saved ? await remove(bookId) : await add(bookId);
    setBusy(false);
    if (!result.ok) toast.error(errorMessage(t, result.error));
    else toast.success(saved ? t('readingList.removed', { title }) : t('readingList.added', { title }));
  };

  const label = saved ? t('readingList.remove', { title }) : t('readingList.add', { title });
  const Icon = saved ? BookmarkCheck : Bookmark;
  return (
    <Button
      type="button"
      variant={saved ? 'secondary' : 'outline'}
      size={withLabel ? 'default' : 'icon'}
      onClick={toggle}
      disabled={busy}
      aria-pressed={saved}
      aria-label={withLabel ? undefined : label}
      title={label}
      className={withLabel ? undefined : 'shrink-0'}
    >
      <Icon className={withLabel ? 'w-4 h-4 mr-2' : 'w-4 h-4'} aria-hidden="true" />
      {withLabel && (saved ? t('readingList.saved') : t('readingList.addShort'))}
    </Button>
  );
}
