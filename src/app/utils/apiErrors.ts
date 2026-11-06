import type { TFunction } from 'i18next';
import { ApiError, NETWORK_ERROR_CODE } from '../../api/errors';

const MESSAGE_KEYS: Record<string, string> = {
  [NETWORK_ERROR_CODE]: 'errors.network',
  INVALID_CREDENTIALS: 'errors.invalidCredentials',
  ACCOUNT_DISABLED: 'errors.accountDisabled',
  EMAIL_ALREADY_EXISTS: 'auth.emailExists',
  INVALID_CURRENT_PASSWORD: 'profile.incorrectPassword',
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
  ORDER_NOT_FOUND: 'errors.notFound',
  USER_NOT_FOUND: 'errors.notFound',
  NOT_FOUND: 'errors.notFound',
};

/** Translated, user-facing message for an API error. */
export function errorMessage(t: TFunction, error: ApiError): string {
  if (error.code === 'BOOK_UNAVAILABLE') {
    const titles = error.unavailableBooks.map((b) => b.title).filter(Boolean);
    return titles.length > 0
      ? t('errors.bookUnavailableList', { titles: titles.join(', ') })
      : t('errors.bookUnavailable');
  }
  if (error.code === 'RENEWAL_NOT_ALLOWED') {
    const reason = String(error.details?.reason ?? '');
    if (reason === 'overdue') return t('errors.renewalOverdue');
    if (reason === 'limit_reached') return t('errors.renewalLimit');
    return t('errors.renewalNotAllowed');
  }
  if (error.code === 'INCOMPLETE_BATCH') {
    const count = Number(error.details?.books_per_batch ?? 0);
    return t('errors.incompleteBatch', { count });
  }
  const key = MESSAGE_KEYS[error.code];
  return key ? t(key) : t('errors.generic');
}
