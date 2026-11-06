import { TFunction } from 'i18next';
import { BookCategory, BookStatus } from '../types';

export const getCategoryTranslation = (t: TFunction, category: BookCategory): string => {
  return t(`categories.${category}`);
};

/** "#1042" for display; falls back to a short id for orders without a number. */
export const orderLabel = (order: { id: string; number?: number }): string =>
  `#${order.number ?? order.id.slice(-6).toUpperCase()}`;

export const getStatusTranslation = (t: TFunction, status: BookStatus): string => {
  switch (status) {
    case 'available':
      return t('bookStatus.available');
    case 'available-soon':
      return t('bookStatus.availableSoon');
    case 'not-available':
      return t('bookStatus.notAvailable');
    case 'pending':
      return t('bookStatus.pending');
  }
};

/** Label of a book's add-to-cart button; always consistent with the status badge. */
export const getCartButtonLabel = (
  t: TFunction,
  { status, inCart, reserved }: { status: BookStatus; inCart: boolean; reserved: boolean },
): string => {
  if (status === 'pending' || inCart) return t('bookStatus.pending');
  if (reserved) return t('bookStatus.notAvailable');
  if (status !== 'available') return getStatusTranslation(t, status);
  return t('bookDetails.addToCart');
};
