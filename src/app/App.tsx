import { RouterProvider } from 'react-router';
import { AuthProvider } from './contexts/AuthContext';
import { CatalogProvider } from './contexts/CatalogContext';
import { CartProvider } from './contexts/CartContext';
import { OrdersProvider } from './contexts/OrdersContext';
import { WaitlistProvider } from './contexts/WaitlistContext';
import { ReadingListProvider } from './contexts/ReadingListContext';
import { HoldsProvider } from './contexts/HoldsContext';
import { ReservationsProvider } from './contexts/ReservationsContext';
import { ReadingLogProvider } from './contexts/ReadingLogContext';
import { FamilyProvider } from './contexts/FamilyContext';
import { Toaster } from './components/ui/sonner';
import { router } from './routes';
import '../i18n/config';

export default function App() {
  return (
    <AuthProvider>
      <CatalogProvider>
        {/* Orders wraps Cart: the cart reports reservation conflicts to the orders state. */}
        <OrdersProvider>
          <CartProvider>
            <WaitlistProvider>
              <ReadingListProvider>
                <HoldsProvider>
                  <ReservationsProvider>
                    <FamilyProvider>
                      <ReadingLogProvider>
                        <RouterProvider router={router} />
                        <Toaster />
                      </ReadingLogProvider>
                    </FamilyProvider>
                  </ReservationsProvider>
                </HoldsProvider>
              </ReadingListProvider>
            </WaitlistProvider>
          </CartProvider>
        </OrdersProvider>
      </CatalogProvider>
    </AuthProvider>
  );
}