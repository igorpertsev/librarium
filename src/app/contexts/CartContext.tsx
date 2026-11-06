import React, { createContext, useContext, useState, ReactNode } from 'react';
import { Book, CartItem, BatchConfig } from '../types';

interface CartContextType {
  cart: CartItem[];
  batchConfig: BatchConfig;
  addBookToCart: (book: Book) => void;
  removeBookFromCart: (batchId: string, bookId: string) => void;
  removeBatch: (batchId: string) => void;
  clearCart: () => void;
  updateBatchConfig: (config: BatchConfig) => void;
  getTotalPrice: () => number;
  isBookInCart: (bookId: string) => boolean;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<CartItem[]>([]);
  const [batchConfig, setBatchConfig] = useState<BatchConfig>({
    booksPerBatch: 5,
    pricePerBatch: 15.99
  });

  const addBookToCart = (book: Book) => {
    setCart(prevCart => {
      const incompleteBatch = prevCart.find(
        batch => batch.books.length < batchConfig.booksPerBatch
      );

      if (incompleteBatch) {
        return prevCart.map(batch =>
          batch.batchId === incompleteBatch.batchId
            ? { ...batch, books: [...batch.books, book] }
            : batch
        );
      } else {
        return [
          ...prevCart,
          {
            batchId: `batch-${Date.now()}`,
            books: [book]
          }
        ];
      }
    });
  };

  const removeBookFromCart = (batchId: string, bookId: string) => {
    setCart(prevCart => {
      const updatedCart = prevCart.map(batch =>
        batch.batchId === batchId
          ? { ...batch, books: batch.books.filter(b => b.id !== bookId) }
          : batch
      );
      return updatedCart.filter(batch => batch.books.length > 0);
    });
  };

  const removeBatch = (batchId: string) => {
    setCart(prevCart => prevCart.filter(batch => batch.batchId !== batchId));
  };

  const clearCart = () => {
    setCart([]);
  };

  const updateBatchConfig = (config: BatchConfig) => {
    setBatchConfig(config);
  };

  const isBookInCart = (bookId: string): boolean => {
    return cart.some(batch => batch.books.some(b => b.id === bookId));
  };

  const getTotalPrice = () => {
    let total = 0;
    cart.forEach(batch => {
      if (batch.books.length === batchConfig.booksPerBatch) {
        total += batchConfig.pricePerBatch;
      }
    });
    return total;
  };

  return (
    <CartContext.Provider
      value={{
        cart,
        batchConfig,
        addBookToCart,
        removeBookFromCart,
        removeBatch,
        clearCart,
        updateBatchConfig,
        getTotalPrice,
        isBookInCart
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
