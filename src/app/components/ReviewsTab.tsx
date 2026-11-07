import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { ModerationReviewPageDto, ReviewStatusDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { Stars } from './Stars';
import { Button } from './ui/button';

const STATUSES: ReviewStatusDto[] = ['pending', 'published', 'rejected'];

/** Admin: written reviews waiting for approval, and the published and rejected ones. */
export function ReviewsTab() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const [status, setStatus] = useState<ReviewStatusDto>('pending');
  const [page, setPage] = useState<ModerationReviewPageDto | null>(null);

  const load = useCallback(async () => {
    setPage(await adminApi.listReviews(status).catch(() => null));
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (action: () => Promise<unknown>, done: string) => {
    const result = await runAction(action);
    if (!result.ok) toast.error(errorMessage(t, result.error));
    else {
      toast.success(done);
      await load();
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg">{t('moderation.title')}</h2>
        <p className="text-sm text-muted-foreground">{t('moderation.description')}</p>
      </div>
      <div role="group" aria-label={t('moderation.filter')} className="flex flex-wrap gap-2">
        {STATUSES.map((key) => (
          <Button
            key={key}
            size="sm"
            variant={key === status ? 'default' : 'outline'}
            aria-pressed={key === status}
            onClick={() => setStatus(key)}
          >
            {t(`moderation.status.${key}`)}
          </Button>
        ))}
      </div>
      {page && page.items.length === 0 && (
        <p className="text-sm text-muted-foreground py-6 text-center">{t('moderation.empty')}</p>
      )}
      <ul className="space-y-3">
        {page?.items.map((review) => (
          <li key={review.id} className="rounded-lg border border-border p-3 space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Stars value={review.rating} size="w-3.5 h-3.5" />
              <span className="font-medium">{review.book_title}</span>
              <span className="text-muted-foreground">
                {review.reader_name} · {review.reader_email} · {fmt.date(review.updated_at)}
              </span>
            </div>
            {review.text && <p className="text-sm whitespace-pre-line">{review.text}</p>}
            <div className="flex flex-wrap gap-2">
              {review.status !== 'published' && (
                <Button
                  size="sm"
                  onClick={() => act(() => adminApi.moderateReview(review.id, 'published'), t('moderation.published'))}
                >
                  <Check className="w-4 h-4 mr-1" aria-hidden="true" />
                  {t('moderation.publish')}
                </Button>
              )}
              {review.status !== 'rejected' && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => act(() => adminApi.moderateReview(review.id, 'rejected'), t('moderation.rejected'))}
                >
                  <X className="w-4 h-4 mr-1" aria-hidden="true" />
                  {t('moderation.reject')}
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => act(() => adminApi.deleteReview(review.id), t('moderation.deleted'))}
                aria-label={t('moderation.deleteNamed', { title: review.book_title })}
              >
                <Trash2 className="w-4 h-4" aria-hidden="true" />
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
