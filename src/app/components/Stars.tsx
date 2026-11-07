import { useTranslation } from 'react-i18next';
import { Star } from 'lucide-react';

/** Read-only stars, e.g. 4.3 -> four full stars and one empty; the number is read out. */
export function Stars({ value, size = 'w-4 h-4' }: { value: number; size?: string }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center" role="img" aria-label={t('reviews.starsLabel', { value })}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          aria-hidden="true"
          className={`${size} ${n <= Math.round(value) ? 'fill-amber-500 text-amber-600' : 'text-muted-foreground'}`}
        />
      ))}
    </span>
  );
}

/** Choosing 1-5 stars: a radio group, so it works with the keyboard and screen readers. */
export function StarInput({ value, onChange, name }: { value: number; onChange: (value: number) => void; name: string }) {
  const { t } = useTranslation();
  return (
    <fieldset className="flex items-center gap-1">
      <legend className="sr-only">{t('reviews.yourRating')}</legend>
      {[1, 2, 3, 4, 5].map((n) => (
        <label key={n} className="cursor-pointer rounded focus-within:ring-2 focus-within:ring-ring">
          <input
            type="radio"
            name={name}
            value={n}
            checked={value === n}
            onChange={() => onChange(n)}
            className="sr-only"
          />
          <span className="sr-only">{t('reviews.starsLabel', { value: n })}</span>
          <Star
            aria-hidden="true"
            className={`w-6 h-6 ${n <= value ? 'fill-amber-500 text-amber-600' : 'text-muted-foreground'}`}
          />
        </label>
      ))}
    </fieldset>
  );
}
