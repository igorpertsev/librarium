import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import { Order, OrderStatus } from '../types';
import { adminApi, fetchAllPages, ordersApi } from '../../api/endpoints';
import { ActionResult, ApiError, runAction, toApiError } from '../../api/errors';
import { orderFromDto } from '../../api/mappers';
import type { OrderDto } from '../../api/types';
import { useAuth } from './AuthContext';
import { useCatalog } from './CatalogContext';

const ACTIVE_STATUSES: ReadonlySet<OrderStatus> = new Set<OrderStatus>(['pending', 'confirmed']);

interface OrdersContextType {
  /** Customers: their own orders. Admins: every order. */
  orders: Order[];
  isLoading: boolean;
  error: ApiError | null;
  /** Creates an order from the server-side cart; price and books are decided by the server. */
  placeOrder: () => Promise<ActionResult<Order>>;
  confirmOrder: (orderId: string) => Promise<ActionResult>;
  markReturned: (orderId: string) => Promise<ActionResult>;
  cancelOrder: (orderId: string) => Promise<ActionResult>;
  /** Customers: extend a borrowed order by one loan period. */
  renewOrder: (orderId: string) => Promise<ActionResult<Order>>;
  updateDueDate: (orderId: string, dueDate: string) => Promise<ActionResult>;
  /** Admins: the reader paid a late fee, or the library waived it. */
  settleLateFee: (orderId: string, action: 'paid' | 'waived') => Promise<ActionResult>;
  /**
   * UX hint only: true if the copy is in an active order we know about. The server makes
   * the final decision when adding to the cart and when the order is placed.
   */
  isBookUnavailable: (bookId: string) => boolean;
  markBooksUnavailable: (bookIds: string[]) => void;
  getOrdersForUser: (userId: string) => Order[];
  refreshOrders: () => Promise<void>;
}

const OrdersContext = createContext<OrdersContextType | undefined>(undefined);

export function OrdersProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { invalidateCatalog } = useCatalog();
  const [orders, setOrders] = useState<Order[]>([]);
  const [knownReserved, setKnownReserved] = useState<ReadonlySet<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const isAdmin = user?.role === 'admin';

  const refreshOrders = useCallback(async () => {
    if (!user) {
      setOrders([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const all = await fetchAllPages((page, page_size) =>
        isAdmin ? adminApi.listOrders({ page, page_size }) : ordersApi.list({ page, page_size }),
      );
      setOrders(all.map(orderFromDto));
    } catch (e) {
      setError(toApiError(e));
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, isAdmin]);

  useEffect(() => {
    setKnownReserved(new Set());
    refreshOrders();
  }, [refreshOrders]);

  const replaceOrder = (dto: OrderDto) => {
    const updated = orderFromDto(dto);
    setOrders((prev) => prev.map((o) => (o.id === updated.id ? updated : o)));
    return updated;
  };

  const markBooksUnavailable = useCallback((bookIds: string[]) => {
    if (bookIds.length === 0) return;
    setKnownReserved((prev) => new Set([...prev, ...bookIds]));
  }, []);

  const placeOrder = async (): Promise<ActionResult<Order>> => {
    const result = await runAction(() => ordersApi.place());
    if (!result.ok) {
      if (result.error.code === 'BOOK_UNAVAILABLE') {
        markBooksUnavailable(result.error.unavailableBookIds);
        invalidateCatalog();
      }
      return result;
    }
    const order = orderFromDto(result.data);
    setOrders((prev) => [order, ...prev]);
    invalidateCatalog();
    return { ok: true, data: order };
  };

  const changeStatus = (orderId: string, status: OrderStatus) =>
    runAction(async () => {
      replaceOrder(await adminApi.setOrderStatus(orderId, status));
      if (!ACTIVE_STATUSES.has(status)) invalidateCatalog();
    });

  const confirmOrder = (orderId: string) => changeStatus(orderId, 'confirmed');
  const markReturned = (orderId: string) => changeStatus(orderId, 'returned');

  const cancelOrder = (orderId: string) =>
    isAdmin
      ? changeStatus(orderId, 'cancelled')
      : runAction(async () => {
          replaceOrder(await ordersApi.cancel(orderId));
          invalidateCatalog();
        });

  const renewOrder = (orderId: string) =>
    runAction(async () => replaceOrder(await ordersApi.renew(orderId)));

  const updateDueDate = (orderId: string, dueDate: string) =>
    runAction(async () => {
      replaceOrder(await adminApi.setOrderDueDate(orderId, dueDate));
    });

  const settleLateFee = (orderId: string, action: 'paid' | 'waived') =>
    runAction(async () => {
      replaceOrder(await adminApi.settleLateFee(orderId, action));
    });

  const isBookUnavailable = (bookId: string): boolean =>
    knownReserved.has(bookId) ||
    orders.some((o) => ACTIVE_STATUSES.has(o.status) && o.books.some((b) => b.id === bookId));

  const getOrdersForUser = (userId: string): Order[] =>
    orders.filter(o => o.userId === userId);

  return (
    <OrdersContext.Provider
      value={{
        orders,
        isLoading,
        error,
        placeOrder,
        confirmOrder,
        markReturned,
        cancelOrder,
        renewOrder,
        updateDueDate,
        settleLateFee,
        isBookUnavailable,
        markBooksUnavailable,
        getOrdersForUser,
        refreshOrders,
      }}
    >
      {children}
    </OrdersContext.Provider>
  );
}

export function useOrders() {
  const context = useContext(OrdersContext);
  if (!context) throw new Error('useOrders must be used within OrdersProvider');
  return context;
}
