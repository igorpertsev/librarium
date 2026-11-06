import { RouterProvider } from 'react-router';
import { AuthProvider } from './contexts/AuthContext';
import { CartProvider } from './contexts/CartContext';
import { OrdersProvider } from './contexts/OrdersContext';
import { Toaster } from './components/ui/sonner';
import { router } from './routes';
import '../i18n/config';

export default function App() {
  return (
    <AuthProvider>
      <CartProvider>
        <OrdersProvider>
          <RouterProvider router={router} />
          <Toaster />
        </OrdersProvider>
      </CartProvider>
    </AuthProvider>
  );
}