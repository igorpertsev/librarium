import { createBrowserRouter, Navigate } from 'react-router';
import { Layout, AdminLayout } from './components/Layout';
import Login from './pages/Login';
import Register from './pages/Register';
import CustomerPortal from './pages/CustomerPortal';
import AdminPortal from './pages/AdminPortal';
import Profile from './pages/Profile';
import Cart from './pages/Cart';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />
  },
  {
    path: '/register',
    element: <Register />
  },
  {
    path: '/',
    element: <Layout />,
    children: [
      {
        index: true,
        element: <CustomerPortal />
      },
      {
        path: 'profile',
        element: <Profile />
      },
      {
        path: 'cart',
        element: <Cart />
      },
      {
        path: 'admin',
        element: <AdminLayout />,
        children: [
          {
            index: true,
            element: <AdminPortal />
          }
        ]
      }
    ]
  },
  {
    path: '*',
    element: <Navigate to="/" replace />
  }
]);
