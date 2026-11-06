export type BookStatus = 'available' | 'available-soon' | 'not-available' | 'pending';

export type BookCategory = 'fiction' | 'non-fiction' | 'children' | 'young-adult' | 'science' | 'history' | 'biography';

/** A subject tag; the catalogue shows the name in the reader's language. */
export interface BookTag {
  slug: string;
  nameEn: string;
  nameRu: string;
}

export interface BookSeries {
  id: string;
  name: string;
}

export interface Book {
  id: string;
  title: string;
  author: string;
  category: BookCategory;
  ageRange: string;
  status: BookStatus;
  coverImage: string;
  images: string[];
  description: string;
  isbn: string;
  publishedYear: number;
  /** Server-computed: the copy belongs to an active order (pending/confirmed). */
  isReserved?: boolean;
  /** Server-computed: active, status "available" and not reserved. */
  isAvailable?: boolean;
  /** While reserved: the due date of the order holding the copy (YYYY-MM-DD). */
  availableFrom?: string | null;
  /** The same for every copy of a title. */
  groupId?: string;
  /** Copies of this title in the library, and how many can be borrowed now. */
  copies?: number;
  copiesAvailable?: number;
  language?: string | null;
  tags?: BookTag[];
  series?: BookSeries | null;
  /** Volume number within the series (may be fractional, e.g. 1.5 for a novella). */
  seriesPosition?: number | null;
}

export type PreferredContact = 'whatsapp' | 'telegram' | 'instagram' | 'phone';

export interface UserContacts {
  whatsapp?: string;
  telegram?: string;
  instagram?: string;
  phone?: string;
  preferred?: PreferredContact;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: 'customer' | 'admin';
  borrowedBooks: BorrowedBook[];
  contacts?: UserContacts;
  /** Interface language saved on the account (emails use it too). */
  preferredLanguage?: UiLanguage | null;
}

export type UiLanguage = 'en' | 'ru';

export interface BorrowedBook {
  bookId: string;
  book: Book;
  borrowedDate: string;
  returnDate: string;
}

export interface CartItem {
  batchId: string;
  books: Book[];
}

export interface BatchConfig {
  booksPerBatch: number;
  pricePerBatch: number;
}

export type OrderStatus = 'pending' | 'confirmed' | 'returned' | 'cancelled';

export interface Order {
  id: string;
  /** Sequential, human-friendly number (#1001). */
  number?: number;
  userId: string;
  userName: string;
  userEmail: string;
  books: Book[];
  status: OrderStatus;
  totalPrice: number;
  orderedAt: string;
  dueDate: string;
  /** How often the customer has extended the loan. */
  renewalCount?: number;
  confirmedAt?: string;
  returnedAt?: string;
  cancelledAt?: string;
  currency?: string;
  /** Contact details captured when the order was placed. */
  contacts?: UserContacts;
}
