import React, { createContext, useContext, useState, ReactNode } from 'react';
import { Order, OrderStatus, Book } from '../types';
import { mockBooks } from '../data/mockBooks';

interface PlaceOrderParams {
  userId: string;
  userName: string;
  userEmail: string;
  books: Book[];
  totalPrice: number;
}

interface OrdersContextType {
  orders: Order[];
  placeOrder: (params: PlaceOrderParams) => void;
  confirmOrder: (orderId: string) => void;
  markReturned: (orderId: string) => void;
  cancelOrder: (orderId: string) => void;
  updateDueDate: (orderId: string, dueDate: string) => void;
  isBookUnavailable: (bookId: string) => boolean;
  getOrdersForUser: (userId: string) => Order[];
}

const OrdersContext = createContext<OrdersContextType | undefined>(undefined);

function daysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().split('T')[0];
}

function daysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().split('T')[0];
}

const seedOrders: Order[] = [
  {
    id: 'order-seed-1',
    userId: '1',
    userName: 'John Customer',
    userEmail: 'customer@library.com',
    books: mockBooks.slice(0, 5),
    status: 'pending',
    totalPrice: 15.99,
    orderedAt: daysAgo(2),
    dueDate: daysFromNow(28),
  },
  {
    id: 'order-seed-2',
    userId: '1',
    userName: 'John Customer',
    userEmail: 'customer@library.com',
    books: mockBooks.slice(5, 10),
    status: 'confirmed',
    totalPrice: 15.99,
    orderedAt: daysAgo(20),
    dueDate: daysFromNow(10),
    confirmedAt: daysAgo(18),
  },
  {
    id: 'order-seed-3',
    userId: '1',
    userName: 'John Customer',
    userEmail: 'customer@library.com',
    books: mockBooks.slice(2, 7),
    status: 'returned',
    totalPrice: 15.99,
    orderedAt: daysAgo(60),
    dueDate: daysAgo(30),
    confirmedAt: daysAgo(58),
    returnedAt: daysAgo(32),
  },
];

export function OrdersProvider({ children }: { children: ReactNode }) {
  const [orders, setOrders] = useState<Order[]>(seedOrders);

  const placeOrder = ({ userId, userName, userEmail, books, totalPrice }: PlaceOrderParams) => {
    const now = new Date().toISOString().split('T')[0];
    const due = new Date();
    due.setDate(due.getDate() + 30);

    const newOrder: Order = {
      id: `order-${Date.now()}`,
      userId,
      userName,
      userEmail,
      books,
      status: 'pending',
      totalPrice,
      orderedAt: now,
      dueDate: due.toISOString().split('T')[0],
    };

    setOrders(prev => [newOrder, ...prev]);
  };

  const confirmOrder = (orderId: string) => {
    const now = new Date().toISOString().split('T')[0];
    setOrders(prev =>
      prev.map(o =>
        o.id === orderId ? { ...o, status: 'confirmed' as OrderStatus, confirmedAt: now } : o
      )
    );
  };

  const markReturned = (orderId: string) => {
    const now = new Date().toISOString().split('T')[0];
    setOrders(prev =>
      prev.map(o =>
        o.id === orderId ? { ...o, status: 'returned' as OrderStatus, returnedAt: now } : o
      )
    );
  };

  const cancelOrder = (orderId: string) => {
    setOrders(prev =>
      prev.map(o =>
        o.id === orderId ? { ...o, status: 'cancelled' as OrderStatus } : o
      )
    );
  };

  const updateDueDate = (orderId: string, dueDate: string) => {
    setOrders(prev =>
      prev.map(o => o.id === orderId ? { ...o, dueDate } : o)
    );
  };

  const isBookUnavailable = (bookId: string): boolean =>
    orders.some(
      o => (o.status === 'pending' || o.status === 'confirmed') &&
      o.books.some(b => b.id === bookId)
    );

  const getOrdersForUser = (userId: string): Order[] =>
    orders.filter(o => o.userId === userId);

  return (
    <OrdersContext.Provider value={{ orders, placeOrder, confirmOrder, markReturned, cancelOrder, updateDueDate, isBookUnavailable, getOrdersForUser }}>
      {children}
    </OrdersContext.Provider>
  );
}

export function useOrders() {
  const context = useContext(OrdersContext);
  if (!context) throw new Error('useOrders must be used within OrdersProvider');
  return context;
}
