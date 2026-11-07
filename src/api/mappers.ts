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
  BookTag,
  BookTranslation,
  BorrowedBook,
  CopyCondition,
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
  BookTranslationDto,
  BookTranslationInDto,
  CartDto,
  LibrarySettingsDto,
  OrderDto,
  OrderItemDto,
  TagBriefDto,
  UserDto,
  UserUpdateDto,
} from './types';
import { mediaUrl, storedMediaUrl } from './media';

const UI_CONTACTS: readonly PreferredContact[] = ['whatsapp', 'telegram', 'instagram', 'phone'];

export function toMoney(value: string | number): number {
  const parsed = typeof value === 'number' ? value : Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function imagesOf(cover: string | null, images: string[]): string[] {
  if (images.length > 0) return images.map((url) => mediaUrl(url));
  return cover ? [mediaUrl(cover)] : [];
}

export function tagFromDto(dto: TagBriefDto): BookTag {
  return { slug: dto.slug, nameEn: dto.name_en, nameRu: dto.name_ru };
}

export function translationFromDto(dto: BookTranslationDto): BookTranslation {
  return {
    language: dto.language,
    title: dto.title,
    author: dto.author,
    description: dto.description,
    titleSource: dto.title_source,
    descriptionSource: dto.description_source,
    sourceUrl: dto.source_url,
  };
}

export function bookFromDto(dto: BookDto | BookBriefDto): Book {
  const book: Book = {
    id: dto.id,
    title: dto.title,
    author: dto.author,
    category: dto.category,
    ageRange: dto.age_range,
    status: dto.status,
    condition: dto.condition,
    conditionNote: dto.condition_note,
    coverImage: dto.cover_url ? mediaUrl(dto.cover_url) : '',
    images: imagesOf(dto.cover_url, dto.image_urls),
    description: dto.description,
    isbn: dto.isbn ?? '',
    publishedYear: dto.publication_year ?? 0,
    language: dto.language,
    groupId: dto.group_id,
    tags: dto.tags.map(tagFromDto),
    series: dto.series
      ? { id: dto.series.id, name: dto.series.name, nameEn: dto.series.name_en, nameRu: dto.series.name_ru }
      : null,
    seriesPosition: dto.series_position,
    translations: dto.translations.map(translationFromDto),
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
  condition: CopyCondition;
  conditionNote: string;
  coverImage: string;
  images: string[];
  description: string;
  isbn: string;
  publishedYear: number;
  /** Tag slugs. */
  tags: string[];
  /** Blank: not in a series. An unknown name creates the series. */
  seriesName: string;
  seriesPosition: number | null;
  /** Open Library series key from an ISBN lookup, so later editions find the same series. */
  seriesOpenlibraryKey?: string | null;
  /** ISO 639-1 code of the book's own language; '' when unknown. */
  language: string;
  /** Translations into the interface languages; one without a title is dropped. */
  translations: BookTranslation[];
}

export function bookFormToDto(form: BookFormValues): BookCreateDto {
  const images = form.images.map((url) => storedMediaUrl(url.trim())).filter(Boolean);
  const cover = storedMediaUrl(form.coverImage.trim());
  return {
    title: form.title,
    author: form.author,
    category: form.category,
    age_range: form.ageRange,
    // "pending" is a UI-only state (book in the cart) and is never persisted.
    status: form.status === 'pending' ? 'available' : form.status,
    condition: form.condition,
    condition_note: form.conditionNote.trim() || null,
    cover_url: cover || null,
    image_urls: images.length > 0 ? images : cover ? [cover] : [],
    description: form.description,
    isbn: form.isbn.trim() || null,
    publication_year: Number.isFinite(form.publishedYear) ? form.publishedYear : null,
    tags: form.tags,
    ...seriesToDto(form),
    language: form.language.trim() || null,
    translations: translationsToDto(form),
  };
}

function translationsToDto(form: BookFormValues): BookTranslationInDto[] {
  return form.translations
    // A "translation" into the book's own language would only hide its real text.
    .filter((item) => item.title.trim() && item.language !== form.language)
    .map((item) => ({
      language: item.language,
      title: item.title.trim(),
      author: item.author.trim(),
      description: item.description.trim(),
      title_source: item.titleSource,
      description_source: item.description.trim() ? item.descriptionSource : 'manual',
      source_url: item.description.trim() ? item.sourceUrl : null,
    }));
}

function seriesToDto(form: BookFormValues): Pick<
  BookCreateDto,
  'series_id' | 'series_name' | 'series_openlibrary_key' | 'series_position'
> {
  const name = form.seriesName.trim();
  // series_id null takes the book out of its series when an edit clears the name.
  if (!name) return { series_id: null };
  return {
    series_name: name,
    series_openlibrary_key: form.seriesOpenlibraryKey || null,
    series_position:
      form.seriesPosition !== null && Number.isFinite(form.seriesPosition) && form.seriesPosition > 0
        ? form.seriesPosition
        : null,
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
  const cover = loan.cover_url ? mediaUrl(loan.cover_url) : '';
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
    mfaEnabled: dto.mfa_enabled,
    telegramConnected: dto.telegram_connected,
    borrowedBooks: 'active_loans' in dto ? dto.active_loans.map(loanToBorrowedBook) : [],
    contacts: contactsFromDto(dto),
    preferredLanguage: dto.preferred_language ?? null,
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
    coverImage: item.cover_url ? mediaUrl(item.cover_url) : current.coverImage,
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
    lateFee: dto.late_fee != null ? toMoney(dto.late_fee) : undefined,
    lateFeeSettledAt: dto.late_fee_settled_at ?? undefined,
    childName: dto.child_name ?? undefined,
    pickup: dto.pickup_point ?? undefined,
    pickupAt: dto.pickup_at ?? undefined,
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
