import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Layers } from 'lucide-react';
import { useCart } from '../contexts/CartContext';
import { Progress } from './ui/progress';
import { Button } from './ui/button';

/**
 * Explains batch lending on the catalogue and shows how far the cart is from the
 * next complete batch (only complete batches can be ordered).
 */
export function BatchProgress() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { cart, batchConfig, currency, isLoaded } = useCart();
  const perBatch = Math.max(batchConfig.booksPerBatch, 1);
  const inCart = cart.reduce((sum, batch) => sum + batch.books.length, 0);
  const completeBatches = Math.floor(inCart / perBatch);
  const inNextBatch = inCart % perBatch;

  // Until the server cart arrives the context holds defaults; never show a wrong price.
  if (!isLoaded) return null;

  let price: string;
  try {
    price = new Intl.NumberFormat(i18n.language, { style: 'currency', currency }).format(
      batchConfig.pricePerBatch,
    );
  } catch {
    price = `${batchConfig.pricePerBatch.toFixed(2)} ${currency}`;
  }

  return (
    <div className="mb-6 rounded-lg border border-border bg-muted/40 p-4 flex flex-col md:flex-row md:items-center gap-3 md:gap-6">
      <div className="flex items-start gap-3 md:flex-1">
        <Layers className="w-5 h-5 mt-0.5 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm">{t('batch.info', { count: perBatch, price })}</p>
      </div>

      <div className="md:w-80 space-y-1.5">
        <div className="flex justify-between text-sm">
          <span>{t('batch.progress', { current: inNextBatch, total: perBatch })}</span>
          {completeBatches > 0 && (
            <span className="text-green-700 dark:text-green-400">
              {t('batch.ready', { count: completeBatches })}
            </span>
          )}
        </div>
        <Progress
          value={(inNextBatch / perBatch) * 100}
          aria-label={t('batch.progress', { current: inNextBatch, total: perBatch })}
        />
      </div>

      {completeBatches > 0 && (
        <Button size="sm" onClick={() => navigate('/cart')}>
          {t('batch.goToCart')}
        </Button>
      )}
    </div>
  );
}
