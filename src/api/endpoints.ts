import { apiRequest } from './client';
import type {
  AdminBookListQuery,
  AdminOrderListQuery,
  AdminUserListQuery,
  AdminUserPageDto,
  AdminUserUpdateDto,
  BookCreateDto,
  BookDto,
  BookListQuery,
  BookPageDto,
  BookStatsDto,
  BookUpdateDto,
  CartDto,
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
  RegisterDto,
  ResetPasswordDto,
  TokenResponseDto,
  UserDto,
  UserUpdateDto,
} from './types';

const id = (value: string) => encodeURIComponent(value);

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
};

export const booksApi = {
  list: (query: BookListQuery, signal?: AbortSignal) =>
    apiRequest<BookPageDto>('/books', { query, signal, auth: false }),
  get: (bookId: string) => apiRequest<BookDto>(`/books/${id(bookId)}`, { auth: false }),
  ageRanges: () => apiRequest<string[]>('/books/age-ranges', { auth: false }),
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

export const libraryApi = {
  rules: () => apiRequest<LibraryRulesDto>('/library/rules', { auth: false }),
};

export const adminApi = {
  listBooks: (query: AdminBookListQuery) => apiRequest<BookPageDto>('/admin/books', { query }),
  bookStats: () => apiRequest<BookStatsDto>('/admin/books/stats'),
  createBook: (body: BookCreateDto) =>
    apiRequest<BookDto>('/admin/books', { method: 'POST', body }),
  updateBook: (bookId: string, body: BookUpdateDto) =>
    apiRequest<BookDto>(`/admin/books/${id(bookId)}`, { method: 'PATCH', body }),
  deleteBook: (bookId: string) =>
    apiRequest<void>(`/admin/books/${id(bookId)}`, { method: 'DELETE' }),
  listUsers: (query: AdminUserListQuery) => apiRequest<AdminUserPageDto>('/admin/users', { query }),
  updateUser: (userId: string, body: AdminUserUpdateDto) =>
    apiRequest<UserDto>(`/admin/users/${id(userId)}`, { method: 'PATCH', body }),
  listOrders: (query: AdminOrderListQuery) => apiRequest<OrderPageDto>('/admin/orders', { query }),
  setOrderStatus: (orderId: string, status: OrderStatusDto) =>
    apiRequest<OrderDto>(`/admin/orders/${id(orderId)}/status`, {
      method: 'PATCH',
      body: { status },
    }),
  setOrderDueDate: (orderId: string, dueDate: string) =>
    apiRequest<OrderDto>(`/admin/orders/${id(orderId)}/due-date`, {
      method: 'PATCH',
      body: { due_date: dueDate },
    }),
  getSettings: () => apiRequest<LibrarySettingsDto>('/admin/settings'),
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
