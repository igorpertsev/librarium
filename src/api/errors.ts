/** Error returned by the backend: `{ error: { code, message, details } }`. */
export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface UnavailableBook {
  id: string;
  title: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? null;
  }

  /** Books listed in a `409 BOOK_UNAVAILABLE` response. */
  get unavailableBooks(): UnavailableBook[] {
    const books = this.details?.books;
    if (!Array.isArray(books)) return [];
    return books.filter(
      (b): b is UnavailableBook =>
        typeof b === 'object' && b !== null && typeof (b as UnavailableBook).id === 'string',
    );
  }

  get unavailableBookIds(): string[] {
    const ids = this.details?.book_ids;
    return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : [];
  }
}

export const NETWORK_ERROR_CODE = 'NETWORK_ERROR';

export function networkError(cause: unknown): ApiError {
  const error = new ApiError(0, {
    code: NETWORK_ERROR_CODE,
    message: cause instanceof Error ? cause.message : 'Network error',
  });
  return error;
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, {
    code: 'UNEXPECTED_ERROR',
    message: error instanceof Error ? error.message : String(error),
  });
}

/** Result of a context action: lets pages show a precise, translated error. */
export type ActionResult<T = void> = { ok: true; data: T } | { ok: false; error: ApiError };

export async function runAction<T>(action: () => Promise<T>): Promise<ActionResult<T>> {
  try {
    return { ok: true, data: await action() };
  } catch (error) {
    return { ok: false, error: toApiError(error) };
  }
}
