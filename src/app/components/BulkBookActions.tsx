import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { QrCode } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { BulkBookUpdateDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { useTagList, useTagName } from '../utils/catalogLists';
import { useConfirm } from './ConfirmDialog';
import { Button } from './ui/button';

type Action = 'status' | 'category' | 'condition' | 'add_tags' | 'remove_tags' | 'deactivate';

const SELECT = 'border border-border rounded-md px-2 py-1.5 text-sm bg-background';
const STATUSES = ['available', 'available-soon', 'not-available'] as const;
const STATUS_KEYS: Record<(typeof STATUSES)[number], string> = {
  available: 'bookStatus.available',
  'available-soon': 'bookStatus.availableSoon',
  'not-available': 'bookStatus.notAvailable',
};
const CATEGORIES = ['fiction', 'non-fiction', 'children', 'young-adult', 'science', 'history', 'biography'] as const;
const CONDITIONS = ['new', 'good', 'worn', 'damaged'] as const;

/** Admin book list: one change for every copy of the selected titles. */
export function BulkBookActions({
  selected,
  onClear,
  onDone,
}: {
  selected: string[];
  onClear: () => void;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { items: tags } = useTagList();
  const tagName = useTagName();
  const { confirm, confirmDialog } = useConfirm();
  const [action, setAction] = useState<Action>('status');
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);

  const options: { value: string; label: string }[] =
    action === 'status'
      ? STATUSES.map((s) => ({ value: s, label: t(STATUS_KEYS[s]) }))
      : action === 'category'
        ? CATEGORIES.map((c) => ({ value: c, label: t(`categories.${c}`) }))
        : action === 'condition'
          ? CONDITIONS.map((c) => ({ value: c, label: t(`condition.${c}`) }))
          : action === 'deactivate'
            ? []
            : tags.map((tag) => ({ value: tag.slug, label: tagName(tag) }));

  const apply = async () => {
    const body: BulkBookUpdateDto = { book_ids: selected, deactivate: false };
    if (action === 'deactivate') {
      const ok = await confirm({
        title: t('bulk.removeTitle', { count: selected.length }),
        description: t('bulk.removeDesc'),
        confirmLabel: t('bulk.remove'),
        destructive: true,
      });
      if (!ok) return;
      body.deactivate = true;
    } else if (!value) {
      return;
    } else if (action === 'add_tags' || action === 'remove_tags') {
      body[action] = [value];
    } else {
      Object.assign(body, { [action]: value });
    }
    setBusy(true);
    const result = await runAction(() => adminApi.bulkUpdateBooks(body));
    setBusy(false);
    if (result.ok) {
      toast.success(t('bulk.done', { count: result.data.titles }));
      setValue('');
      onDone();
    } else {
      toast.error(errorMessage(t, result.error));
    }
  };

  return (
    <div
      role="region"
      aria-label={t('bulk.region')}
      className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-primary/40 bg-primary/5 p-3"
    >
      <span className="text-sm font-medium">{t('bulk.selected', { count: selected.length })}</span>
      <select
        aria-label={t('bulk.action')}
        className={SELECT}
        value={action}
        onChange={(e) => {
          setAction(e.target.value as Action);
          setValue('');
        }}
      >
        {(['status', 'category', 'condition', 'add_tags', 'remove_tags', 'deactivate'] as const).map((key) => (
          <option key={key} value={key}>
            {t(`bulk.actions.${key}`)}
          </option>
        ))}
      </select>
      {action !== 'deactivate' && (
        <select aria-label={t('bulk.value')} className={SELECT} value={value} onChange={(e) => setValue(e.target.value)}>
          <option value="">{t('bulk.choose')}</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
      <Button
        size="sm"
        variant={action === 'deactivate' ? 'destructive' : 'default'}
        onClick={apply}
        disabled={busy || (action !== 'deactivate' && !value)}
      >
        {t('bulk.apply')}
      </Button>
      <Button asChild size="sm" variant="outline">
        <Link to={`/admin/labels?ids=${selected.join(',')}`}>
          <QrCode className="w-4 h-4 mr-1" aria-hidden="true" />
          {t('labels.printSelected')}
        </Link>
      </Button>
      <Button size="sm" variant="ghost" onClick={onClear}>
        {t('bulk.clear')}
      </Button>
      {confirmDialog}
    </div>
  );
}
