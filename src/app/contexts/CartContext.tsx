import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import { Book, CartItem, BatchConfig } from '../types';
import { adminApi, cartApi } from '../../api/endpoints';
import { ActionResult, ApiError, runAction, toApiError } from '../../api/errors';
import { CartView, cartFromDto } from '../../api/mappers';
import type { CartDto } from '../../api/types';
import { useAuth } from './AuthContext';
import { useCatalog } from './CatalogContext';
import { useOrders } from './OrdersContext';

interface CartContextType {
  /** Books grouped into batches; batches are computed by the server in insertion order. */
  cart: CartItem[];
  batchConfig: BatchConfig;
  currency: string;
  isLoading: boolean;
  error: ApiError | null;
  /** Cart books that can no longer be ordered (reserved, withdrawn or not available). */
  unavailableBookIds: ReadonlySet<string>;
  addBookToCart: (book: Book) => Promise<ActionResult>;
  removeBookFromCart: (batchId: string, bookId: string) => Promise<ActionResult>;
  removeBatch: (batchId: string) => Promise<ActionResult>;
  clearCart: () => Promise<ActionResult>;
  /** Admin: persist the batch configuration on the server. */
  updateBatchConfig: (config: BatchConfig) => Promise<ActionResult>;
  getTotalPrice: () => number;
  isBookInCart: (bookId: string) => boolean;
  refreshCart: () => Promise<void>;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

const EMPTY_CART: CartView = {
  batches: [],
  batchConfig: { booksPerBatch: 5, pricePerBatch: 15.99 },
  currency: 'USD',
  totalPrice: 0,
  unavailableBookIds: new Set(),
};

export function CartProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { markBooksUnavailable } = useOrders();
  const { invalidateCatalog } = useCatalog();
  const [view, setView] = useState<CartView>(EMPTY_CART);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const apply = (dto: CartDto) => setView(cartFromDto(dto));

  const refreshCart = useCallback(async () => {
    if (!user) {
      setView(EMPTY_CART);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      setView(cartFromDto(await cartApi.get()));
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    refreshCart();
  }, [refreshCart]);

  const addBookToCart = async (book: Book): Promise<ActionResult> => {
    const result = await runAction(() => cartApi.add(book.id));
    if (result.ok) {
      apply(result.data);
      return { ok: true, data: undefined };
    }
    if (result.error.code === 'BOOK_UNAVAILABLE') {
      // The server is the source of truth: remember the conflict and refresh the catalogue.
      markBooksUnavailable(result.error.unavailableBookIds);
      invalidateCatalog();
    }
    return result;
  };

  const removeBookFromCart = (_batchId: string, bookId: string) =>
    runAction(async () => apply(await cartApi.remove(bookId)));

  const removeBatch = (batchId: string) =>
    runAction(async () => {
      const batch = view.batches.find((b) => b.batchId === batchId);
      let latest: CartDto | undefined;
      for (const book of batch?.books ?? []) {
        latest = await cartApi.remove(book.id);
      }
      if (latest) apply(latest);
    });

  const clearCart = () => runAction(async () => apply(await cartApi.clear()));

  const updateBatchConfig = (config: BatchConfig) =>
    runAction(async () => {
      await adminApi.updateSettings({
        books_per_batch: config.booksPerBatch,
        price_per_batch: config.pricePerBatch.toFixed(2),
      });
      apply(await cartApi.get());
    });

  const isBookInCart = (bookId: string): boolean =>
    view.batches.some((batch) => batch.books.some((b) => b.id === bookId));

  const getTotalPrice = () => view.totalPrice;

  return (
    <CartContext.Provider
      value={{
        cart: view.batches,
        batchConfig: view.batchConfig,
        currency: view.currency,
        isLoading,
        error,
        unavailableBookIds: view.unavailableBookIds,
        addBookToCart,
        removeBookFromCart,
        removeBatch,
        clearCart,
        updateBatchConfig,
        getTotalPrice,
        isBookInCart,
        refreshCart,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error('useCart must be used within CartProvider');
  }
  return context;
}
