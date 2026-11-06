export type BookStatus = 'available' | 'available-soon' | 'not-available' | 'pending';

export type BookCategory = 'fiction' | 'non-fiction' | 'children' | 'young-adult' | 'science' | 'history' | 'biography';

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
}

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
  userId: string;
  userName: string;
  userEmail: string;
  books: Book[];
  status: OrderStatus;
  totalPrice: number;
  orderedAt: string;
  dueDate: string;
  confirmedAt?: string;
  returnedAt?: string;
}
