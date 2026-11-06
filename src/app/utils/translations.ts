import { TFunction } from 'i18next';
import { BookCategory, BookStatus } from '../types';

export const getCategoryTranslation = (t: TFunction, category: BookCategory): string => {
  return t(`categories.${category}`);
};

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
