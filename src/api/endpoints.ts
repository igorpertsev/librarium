import { apiDownload, apiRequest } from './client';
import type {
  AdminBookListQuery,
  AdminOrderListQuery,
  AdminUserListQuery,
  AdminUserPageDto,
  AdminUserUpdateDto,
  BookCreateDto,
  BookImportResultDto,
  BookLookupDto,
  BookDto,
  BookListQuery,
  BookPageDto,
  BookStatsDto,
  BookUpdateDto,
  CartDto,
  DemandDto,
  ChangePasswordDto,
  ForgotPasswordDto,
  LibraryRulesDto,
  LibrarySettingsDto,
  LibrarySettingsUpdateDto,
  LoginDto,
  OrderDto,
  OrderListQuery,
  OrderPageDto,
  OrderStatusDto,
  Paged,
  QualitySummaryDto,
  ReadingListItemDto,
  SeriesNeighboursDto,
  RegisterDto,
  ReminderQueuedDto,
  ResetPasswordDto,
  ReportSummaryDto,
  SeriesCreateDto,
  SeriesDto,
  SeriesUpdateDto,
  TagCreateDto,
  TagDto,
  TagUpdateDto,
  TokenResponseDto,
  TranslationSuggestRequestDto,
  TranslationSuggestionDto,
  UserDto,
  UserUpdateDto,
  WaitlistEntryDto,
} from './types';

const id = (value: string) => encodeURIComponent(value);

export interface ReportPeriod {
  date_from: string;
  date_to: string;
}

export const authApi = {
  register: (body: RegisterDto) =>
    apiRequest<TokenResponseDto>('/auth/register', { method: 'POST', body, auth: false }),
  login: (body: LoginDto) =>
    apiRequest<TokenResponseDto>('/auth/login', { method: 'POST', body, auth: false }),
  logout: () => apiRequest<void>('/auth/logout', { method: 'POST', auth: false }),
  me: () => apiRequest<UserDto>('/auth/me'),
  changePassword: (body: ChangePasswordDto) =>
    apiRequest<TokenResponseDto>('/auth/change-password', { method: 'POST', body }),
  forgotPassword: (body: ForgotPasswordDto) =>
    apiRequest<void>('/auth/forgot-password', { method: 'POST', body, auth: false }),
  resetPassword: (body: ResetPasswordDto) =>
    apiRequest<void>('/auth/reset-password', { method: 'POST', body, auth: false }),
};

export const usersApi = {
  updateMe: (body: UserUpdateDto) => apiRequest<UserDto>('/users/me', { method: 'PATCH', body }),
  nextInSeries: () => apiRequest<BookDto[]>('/users/me/next-in-series'),
  recommendations: () => apiRequest<BookDto[]>('/users/me/recommendations'),
  exportData: () => apiDownload('/users/me/export'),
  deleteMe: (password: string) =>
    apiRequest<void>('/users/me', { method: 'DELETE', body: { password } }),
};

export const booksApi = {
  list: (query: BookListQuery, signal?: AbortSignal) =>
    apiRequest<BookPageDto>('/books', { query, signal, auth: false }),
  get: (bookId: string) => apiRequest<BookDto>(`/books/${id(bookId)}`, { auth: false }),
  ageRanges: () => apiRequest<string[]>('/books/age-ranges', { auth: false }),
  languages: () => apiRequest<string[]>('/books/languages', { auth: false }),
  alsoBorrowed: (bookId: string) =>
    apiRequest<BookDto[]>(`/books/${id(bookId)}/also-borrowed`, { auth: false }),
  seriesNeighbours: (bookId: string) =>
    apiRequest<SeriesNeighboursDto>(`/books/${id(bookId)}/series-neighbours`, { auth: false }),
};

export const catalogApi = {
  tags: () => apiRequest<TagDto[]>('/tags', { auth: false }),
  series: (q?: string) => apiRequest<SeriesDto[]>('/series', { query: { q }, auth: false }),
  getSeries: (seriesId: string) =>
    apiRequest<SeriesDto>(`/series/${id(seriesId)}`, { auth: false }),
};

export const cartApi = {
  get: () => apiRequest<CartDto>('/cart'),
  add: (bookId: string) =>
    apiRequest<CartDto>('/cart/items', { method: 'POST', body: { book_id: bookId } }),
  remove: (bookId: string) => apiRequest<CartDto>(`/cart/items/${id(bookId)}`, { method: 'DELETE' }),
  clear: () => apiRequest<CartDto>('/cart', { method: 'DELETE' }),
};

export const ordersApi = {
  place: () => apiRequest<OrderDto>('/orders', { method: 'POST' }),
  list: (query: OrderListQuery) => apiRequest<OrderPageDto>('/orders', { query }),
  get: (orderId: string) => apiRequest<OrderDto>(`/orders/${id(orderId)}`),
  cancel: (orderId: string) =>
    apiRequest<OrderDto>(`/orders/${id(orderId)}/cancel`, { method: 'POST' }),
  renew: (orderId: string) =>
    apiRequest<OrderDto>(`/orders/${id(orderId)}/renew`, { method: 'POST' }),
};

export const waitlistApi = {
  list: () => apiRequest<WaitlistEntryDto[]>('/waitlist'),
  join: (bookId: string) =>
    apiRequest<WaitlistEntryDto>(`/waitlist/${id(bookId)}`, { method: 'POST' }),
  leave: (bookId: string) => apiRequest<void>(`/waitlist/${id(bookId)}`, { method: 'DELETE' }),
};

export const readingListApi = {
  list: () => apiRequest<ReadingListItemDto[]>('/reading-list'),
  add: (bookId: string) => apiRequest<void>(`/reading-list/${id(bookId)}`, { method: 'POST' }),
  remove: (bookId: string) => apiRequest<void>(`/reading-list/${id(bookId)}`, { method: 'DELETE' }),
};

export const libraryApi = {
  rules: () => apiRequest<LibraryRulesDto>('/library/rules', { auth: false }),
};

export const adminApi = {
  listBooks: (query: AdminBookListQuery) => apiRequest<BookPageDto>('/admin/books', { query }),
  bookStats: () => apiRequest<BookStatsDto>('/admin/books/stats'),
  bookQuality: () => apiRequest<QualitySummaryDto>('/admin/books/quality'),
  findDuplicates: (query: { isbn?: string; title?: string; author?: string }) =>
    apiRequest<BookDto[]>('/admin/books/duplicates', { query }),
  lookupIsbn: (isbn: string) => apiRequest<BookLookupDto>(`/admin/isbn/${id(isbn)}`),
  importBooks: (csv: string, dryRun: boolean) =>
    apiRequest<BookImportResultDto>('/admin/books/import', {
      method: 'POST',
      body: { csv },
      query: { dry_run: dryRun },
    }),
  addCopies: (bookId: string, count = 1) =>
    apiRequest<BookDto[]>(`/admin/books/${id(bookId)}/copies`, { method: 'POST', body: { count } }),
  createBook: (body: BookCreateDto) =>
    apiRequest<BookDto>('/admin/books', { method: 'POST', body }),
  updateBook: (bookId: string, body: BookUpdateDto) =>
    apiRequest<BookDto>(`/admin/books/${id(bookId)}`, { method: 'PATCH', body }),
  deleteBook: (bookId: string) =>
    apiRequest<void>(`/admin/books/${id(bookId)}`, { method: 'DELETE' }),
  suggestTranslation: (body: TranslationSuggestRequestDto) =>
    apiRequest<TranslationSuggestionDto>('/admin/translations/suggest', { method: 'POST', body }),
  createTag: (body: TagCreateDto) => apiRequest<TagDto>('/admin/tags', { method: 'POST', body }),
  updateTag: (tagId: string, body: TagUpdateDto) =>
    apiRequest<TagDto>(`/admin/tags/${id(tagId)}`, { method: 'PATCH', body }),
  deleteTag: (tagId: string) => apiRequest<void>(`/admin/tags/${id(tagId)}`, { method: 'DELETE' }),
  mergeTag: (tagId: string, intoId: string) =>
    apiRequest<void>(`/admin/tags/${id(tagId)}/merge`, { method: 'POST', body: { into_id: intoId } }),
  createSeries: (body: SeriesCreateDto) =>
    apiRequest<SeriesDto>('/admin/series', { method: 'POST', body }),
  updateSeries: (seriesId: string, body: SeriesUpdateDto) =>
    apiRequest<SeriesDto>(`/admin/series/${id(seriesId)}`, { method: 'PATCH', body }),
  deleteSeries: (seriesId: string) =>
    apiRequest<void>(`/admin/series/${id(seriesId)}`, { method: 'DELETE' }),
  mergeSeries: (seriesId: string, intoId: string) =>
    apiRequest<void>(`/admin/series/${id(seriesId)}/merge`, {
      method: 'POST',
      body: { into_id: intoId },
    }),
  listUsers: (query: AdminUserListQuery) => apiRequest<AdminUserPageDto>('/admin/users', { query }),
  updateUser: (userId: string, body: AdminUserUpdateDto) =>
    apiRequest<UserDto>(`/admin/users/${id(userId)}`, { method: 'PATCH', body }),
  listOrders: (query: AdminOrderListQuery) => apiRequest<OrderPageDto>('/admin/orders', { query }),
  setOrderStatus: (orderId: string, status: OrderStatusDto) =>
    apiRequest<OrderDto>(`/admin/orders/${id(orderId)}/status`, {
      method: 'PATCH',
      body: { status },
    }),
  remindCustomer: (orderId: string) =>
    apiRequest<ReminderQueuedDto>(`/admin/orders/${id(orderId)}/remind`, { method: 'POST' }),
  setOrderDueDate: (orderId: string, dueDate: string) =>
    apiRequest<OrderDto>(`/admin/orders/${id(orderId)}/due-date`, {
      method: 'PATCH',
      body: { due_date: dueDate },
    }),
  getSettings: () => apiRequest<LibrarySettingsDto>('/admin/settings'),
  reportSummary: (period: ReportPeriod) =>
    apiRequest<ReportSummaryDto>('/admin/reports/summary', { query: period }),
  reportDemand: (period: ReportPeriod) =>
    apiRequest<DemandDto>('/admin/reports/demand', { query: period }),
  ordersCsv: (period: ReportPeriod) => apiDownload('/admin/reports/orders.csv', { query: period }),
  updateSettings: (body: LibrarySettingsUpdateDto) =>
    apiRequest<LibrarySettingsDto>('/admin/settings', { method: 'PATCH', body }),
};

/** Load every page of a paginated endpoint (bounded, for small admin lists). */
export async function fetchAllPages<T>(
  load: (page: number, pageSize: number) => Promise<Paged<T>>,
  { pageSize = 100, maxPages = 50 }: { pageSize?: number; maxPages?: number } = {},
): Promise<T[]> {
  const items: T[] = [];
  for (let page = 1; page <= maxPages; page += 1) {
    const result = await load(page, pageSize);
    items.push(...result.items);
    if (items.length >= result.total || result.items.length === 0) break;
  }
  return items;
}
