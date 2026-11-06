/**
 * Adapters between backend DTOs (snake_case, generated from OpenAPI) and the existing UI
 * models in `src/app/types.ts`, so components did not have to be rewritten.
 *
 * Documented differences:
 * - Book: `cover_url`/`image_urls`/`publication_year`/`age_range` ↔ `coverImage`/`images`/
 *   `publishedYear`/`ageRange`. The server adds `is_reserved`/`is_available`; the UI-only
 *   status `pending` ("in my cart") is never stored.
 * - Money is a decimal string on the wire ("15.99") and a number in the UI (display only;
 *   totals are always computed by the server).
 * - Preferred contact: the backend also accepts `email`, which the UI has no control for; it
 *   maps to "no preference" in the UI.
 * - Cart batches are derived by the server (`batch_number`) instead of being stored.
 */
import type {
  BatchConfig,
  Book,
  BookStatus,
  BorrowedBook,
  CartItem,
  Order,
  PreferredContact,
  User,
  UserContacts,
} from '../app/types';
import type {
  ActiveLoanDto,
  AdminUserDto,
  BookBriefDto,
  BookCreateDto,
  BookDto,
  CartDto,
  LibrarySettingsDto,
  OrderDto,
  OrderItemDto,
  UserDto,
  UserUpdateDto,
} from './types';

const UI_CONTACTS: readonly PreferredContact[] = ['whatsapp', 'telegram', 'instagram', 'phone'];

export function toMoney(value: string | number): number {
  const parsed = typeof value === 'number' ? value : Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function imagesOf(cover: string | null, images: string[]): string[] {
  if (images.length > 0) return images;
  return cover ? [cover] : [];
}

export function bookFromDto(dto: BookDto | BookBriefDto): Book {
  const book: Book = {
    id: dto.id,
    title: dto.title,
    author: dto.author,
    category: dto.category,
    ageRange: dto.age_range,
    status: dto.status,
    coverImage: dto.cover_url ?? '',
    images: imagesOf(dto.cover_url, dto.image_urls),
    description: dto.description,
    isbn: dto.isbn ?? '',
    publishedYear: dto.publication_year ?? 0,
    language: dto.language,
  };
  if ('is_reserved' in dto) {
    book.isReserved = dto.is_reserved;
    book.isAvailable = dto.is_available;
    book.availableFrom = dto.available_from;
    book.copies = dto.copies;
    book.copiesAvailable = dto.copies_available;
  }
  return book;
}

export interface BookFormValues {
  title: string;
  author: string;
  category: Book['category'];
  ageRange: string;
  status: BookStatus;
  coverImage: string;
  images: string[];
  description: string;
  isbn: string;
  publishedYear: number;
}

export function bookFormToDto(form: BookFormValues): BookCreateDto {
  const images = form.images.map((url) => url.trim()).filter(Boolean);
  const cover = form.coverImage.trim();
  return {
    title: form.title,
    author: form.author,
    category: form.category,
    age_range: form.ageRange,
    // "pending" is a UI-only state (book in the cart) and is never persisted.
    status: form.status === 'pending' ? 'available' : form.status,
    cover_url: cover || null,
    image_urls: images.length > 0 ? images : cover ? [cover] : [],
    description: form.description,
    isbn: form.isbn.trim() || null,
    publication_year: Number.isFinite(form.publishedYear) ? form.publishedYear : null,
  };
}

function contactsFromDto(dto: UserDto): UserContacts {
  const preferred = dto.preferred_contact_method;
  return {
    whatsapp: dto.whatsapp ?? undefined,
    telegram: dto.telegram ?? undefined,
    instagram: dto.instagram ?? undefined,
    phone: dto.phone ?? undefined,
    preferred: preferred && UI_CONTACTS.includes(preferred as PreferredContact)
      ? (preferred as PreferredContact)
      : undefined,
  };
}

/** UI contact form → PATCH body. Empty values become `null` (= remove the contact). */
export function contactsToDto(contacts: UserContacts): Pick<
  UserUpdateDto,
  'whatsapp' | 'telegram' | 'instagram' | 'phone' | 'preferred_contact_method'
> {
  return {
    whatsapp: contacts.whatsapp ?? null,
    telegram: contacts.telegram ?? null,
    instagram: contacts.instagram ?? null,
    phone: contacts.phone ?? null,
    preferred_contact_method: contacts.preferred ?? null,
  };
}

function loanToBorrowedBook(loan: ActiveLoanDto): BorrowedBook {
  const cover = loan.cover_url ?? '';
  return {
    bookId: loan.book_id,
    book: {
      id: loan.book_id,
      title: loan.title,
      author: loan.author,
      category: 'fiction',
      ageRange: '',
      status: 'not-available',
      coverImage: cover,
      images: cover ? [cover] : [],
      description: '',
      isbn: '',
      publishedYear: 0,
    },
    borrowedDate: loan.borrowed_at ?? '',
    returnDate: loan.due_date,
  };
}

export function userFromDto(dto: UserDto | AdminUserDto): User {
  return {
    id: dto.id,
    name: dto.full_name,
    email: dto.email,
    role: dto.role,
    borrowedBooks: 'active_loans' in dto ? dto.active_loans.map(loanToBorrowedBook) : [],
    contacts: contactsFromDto(dto),
  };
}

function orderItemToBook(item: OrderItemDto): Book {
  // Title, author and cover come from the immutable snapshot; the rest is current data.
  const current = bookFromDto(item.book);
  return {
    ...current,
    id: item.book_id,
    title: item.title,
    author: item.author,
    isbn: item.isbn ?? '',
    category: item.category,
    ageRange: item.age_range,
    coverImage: item.cover_url ?? current.coverImage,
  };
}

export function orderFromDto(dto: OrderDto): Order {
  const preferred = dto.contact_preferred_method;
  return {
    id: dto.id,
    number: dto.number,
    userId: dto.user_id,
    userName: dto.contact_name,
    userEmail: dto.contact_email,
    books: dto.items.map(orderItemToBook),
    status: dto.status,
    totalPrice: toMoney(dto.total_amount),
    currency: dto.currency,
    orderedAt: dto.created_at,
    dueDate: dto.due_date,
    renewalCount: dto.renewal_count,
    confirmedAt: dto.confirmed_at ?? undefined,
    returnedAt: dto.returned_at ?? undefined,
    cancelledAt: dto.cancelled_at ?? undefined,
    contacts: {
      whatsapp: dto.contact_whatsapp ?? undefined,
      telegram: dto.contact_telegram ?? undefined,
      instagram: dto.contact_instagram ?? undefined,
      phone: dto.contact_phone ?? undefined,
      preferred: preferred && UI_CONTACTS.includes(preferred as PreferredContact)
        ? (preferred as PreferredContact)
        : undefined,
    },
  };
}

export interface CartView {
  batches: CartItem[];
  batchConfig: BatchConfig;
  currency: string;
  totalPrice: number;
  unavailableBookIds: Set<string>;
}

export function cartFromDto(dto: CartDto): CartView {
  const batches = new Map<number, CartItem>();
  const unavailable = new Set<string>();
  for (const item of dto.items) {
    const key = item.batch_number;
    const batch = batches.get(key) ?? { batchId: `batch-${key}`, books: [] };
    batch.books.push(bookFromDto(item.book));
    batches.set(key, batch);
    if (!item.book.is_available) unavailable.add(item.book.id);
  }
  return {
    batches: [...batches.values()],
    batchConfig: {
      booksPerBatch: dto.books_per_batch,
      pricePerBatch: toMoney(dto.price_per_batch),
    },
    currency: dto.currency,
    totalPrice: toMoney(dto.total_amount),
    unavailableBookIds: unavailable,
  };
}

export function batchConfigFromSettings(dto: LibrarySettingsDto): BatchConfig {
  return { booksPerBatch: dto.books_per_batch, pricePerBatch: toMoney(dto.price_per_batch) };
}
