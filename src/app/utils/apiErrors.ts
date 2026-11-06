import type { TFunction } from 'i18next';
import { ApiError, NETWORK_ERROR_CODE } from '../../api/errors';

const MESSAGE_KEYS: Record<string, string> = {
  [NETWORK_ERROR_CODE]: 'errors.network',
  INVALID_CREDENTIALS: 'errors.invalidCredentials',
  ACCOUNT_DISABLED: 'errors.accountDisabled',
  EMAIL_ALREADY_EXISTS: 'auth.emailExists',
  INVALID_CURRENT_PASSWORD: 'profile.incorrectPassword',
  INVALID_RESET_TOKEN: 'auth.invalidResetLink',
  PASSWORD_UNCHANGED: 'errors.passwordUnchanged',
  VALIDATION_ERROR: 'errors.validation',
  NOT_AUTHENTICATED: 'errors.sessionExpired',
  TOKEN_EXPIRED: 'errors.sessionExpired',
  FORBIDDEN: 'errors.forbidden',
  CART_EMPTY: 'cart.empty',
  INVALID_STATUS_TRANSITION: 'errors.invalidTransition',
  ORDER_NOT_ACTIVE: 'errors.invalidTransition',
  INVALID_DUE_DATE: 'errors.invalidDueDate',
  CANNOT_MODIFY_SELF: 'errors.cannotModifySelf',
  BOOK_NOT_FOUND: 'errors.bookNotFound',
  BOOK_AVAILABLE: 'waitlist.availableNow',
  ORDER_NOT_FOUND: 'errors.notFound',
  REMINDER_RECENTLY_SENT: 'errors.reminderRecentlySent',
  ORDER_NOT_BORROWED: 'errors.invalidTransition',
  INVALID_PERIOD: 'errors.invalidPeriod',
  USER_NOT_FOUND: 'errors.notFound',
  NOT_FOUND: 'errors.notFound',
  TAG_NOT_FOUND: 'errors.tagNotFound',
  ACTIVE_ORDERS: 'errors.activeOrders',
  NOT_BORROWED: 'errors.notBorrowed',
  REVIEW_NOT_FOUND: 'errors.notFound',
  ADMIN_ACCOUNT: 'errors.adminAccount',
  TAG_EXISTS: 'errors.tagExists',
  TAG_SLUG: 'errors.tagSlug',
  SAME_TAG: 'errors.sameMergeTarget',
  SERIES_NOT_FOUND: 'errors.seriesNotFound',
  SERIES_EXISTS: 'errors.seriesExists',
  SAME_SERIES: 'errors.sameMergeTarget',
};

/** Translated, user-facing message for an API error. */
export function errorMessage(t: TFunction, error: ApiError): string {
  if (error.code === 'BOOK_UNAVAILABLE') {
    const titles = error.unavailableBooks.map((b) => b.title).filter(Boolean);
    return titles.length > 0
      ? t('errors.bookUnavailableList', { titles: titles.join(', ') })
      : t('errors.bookUnavailable');
  }
  if (error.code === 'TOO_MANY_REQUESTS') {
    const seconds = Number(error.details?.retry_after ?? 60);
    return t('errors.tooManyAttempts', { count: Math.max(1, Math.ceil(seconds / 60)) });
  }
  if (error.code === 'INTERNAL_ERROR' && typeof error.details?.request_id === 'string') {
    return t('errors.genericWithReference', { id: error.details.request_id });
  }
  if (error.code === 'RENEWAL_NOT_ALLOWED') {
    const reason = String(error.details?.reason ?? '');
    if (reason === 'overdue') return t('errors.renewalOverdue');
    if (reason === 'limit_reached') return t('errors.renewalLimit');
    if (reason === 'requested_by_others') return t('errors.renewalRequested');
    return t('errors.renewalNotAllowed');
  }
  if (error.code === 'INCOMPLETE_BATCH') {
    const count = Number(error.details?.books_per_batch ?? 0);
    return t('errors.incompleteBatch', { count });
  }
  if (error.code === 'UNKNOWN_TAGS') {
    const tags = Array.isArray(error.details?.tags) ? error.details.tags.join(', ') : '';
    return t('errors.unknownTags', { tags });
  }
  const key = MESSAGE_KEYS[error.code];
  return key ? t(key) : t('errors.generic');
}
