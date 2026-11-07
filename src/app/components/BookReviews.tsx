import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { booksApi, reviewsApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { MyReviewDto, ReviewSummaryDto } from '../../api/types';
import { useAuth } from '../contexts/AuthContext';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { StarInput, Stars } from './Stars';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';

const SHOWN = 5;

/** Book dialog: the title's rating and reviews, and the reader's own review. */
export function BookReviews({ bookId }: { bookId: string }) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const { user } = useAuth();
  const [summary, setSummary] = useState<ReviewSummaryDto | null>(null);
  const [mine, setMine] = useState<MyReviewDto | null>(null);
  const [rating, setRating] = useState(0);
  const [text, setText] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setSummary(await booksApi.reviews(bookId).catch(() => null));
    if (user) {
      const own = await reviewsApi.mine(bookId).catch(() => null);
      setMine(own);
      setRating(own?.review?.rating ?? 0);
      setText(own?.review?.text ?? '');
    }
  }, [bookId, user]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const result = await runAction(() => reviewsApi.save(bookId, { rating, text: text.trim() }));
    setSaving(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    toast.success(result.data.status === 'pending' ? t('reviews.sentForApproval') : t('reviews.saved'));
    await load();
  };

  const remove = async () => {
    const result = await runAction(() => reviewsApi.remove(bookId));
    if (!result.ok) toast.error(errorMessage(t, result.error));
    else {
      toast.success(t('reviews.deleted'));
      await load();
    }
  };

  const reviews = summary?.reviews ?? [];
  const shown = showAll ? reviews : reviews.slice(0, SHOWN);
  return (
    <section aria-labelledby={`reviews-${bookId}`} className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 id={`reviews-${bookId}`} className="text-base sm:text-xl">{t('reviews.title')}</h3>
        {summary && summary.average !== null ? (
          <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <Stars value={summary.average} />
            {t('reviews.average', { average: summary.average.toLocaleString(), count: summary.count })}
          </span>
        ) : (
          <span className="text-sm text-muted-foreground">{t('reviews.none')}</span>
        )}
      </div>

      {shown.length > 0 && (
        <ul className="space-y-3">
          {shown.map((review) => (
            <li key={review.id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Stars value={review.rating} size="w-3.5 h-3.5" />
                <span className="font-medium">{review.author_name}</span>
                <span className="text-muted-foreground">{fmt.date(review.created_at)}</span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground whitespace-pre-line">{review.text}</p>
            </li>
          ))}
        </ul>
      )}
      {reviews.length > SHOWN && (
        <Button variant="link" size="sm" className="px-0" onClick={() => setShowAll(!showAll)}>
          {showAll ? t('reviews.showFewer') : t('reviews.showAll', { count: reviews.length })}
        </Button>
      )}

      {mine?.can_review && (
        <form onSubmit={save} className="space-y-2 rounded-lg bg-muted/40 p-3">
          <p className="text-sm font-medium">{mine.review ? t('reviews.yourReview') : t('reviews.rateIt')}</p>
          <StarInput name={`rating-${bookId}`} value={rating} onChange={setRating} />
          <div className="space-y-1">
            <Label htmlFor={`review-text-${bookId}`}>{t('reviews.textLabel')}</Label>
            <Textarea
              id={`review-text-${bookId}`}
              rows={3}
              maxLength={2000}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {mine.review?.status === 'pending'
              ? t('reviews.pendingNote')
              : mine.review?.status === 'rejected'
                ? t('reviews.rejectedNote')
                : t('reviews.moderationNote')}
          </p>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={saving || rating === 0}>{t('reviews.save')}</Button>
            {mine.review && (
              <Button type="button" size="sm" variant="ghost" onClick={remove}>{t('reviews.delete')}</Button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
