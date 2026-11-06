import { createBrowserRouter, Navigate } from 'react-router';
import { Layout, AdminLayout } from './components/Layout';
import Login from './pages/Login';

// Pages are loaded when first opened, so the sign-in page and the catalogue do not wait for
// the admin portal's code (see "Code splitting" in README.md). Login stays in the main bundle.
const RELOAD_FLAG = 'librarium:reloaded-for-new-version';

const page = (load: () => Promise<{ default: React.ComponentType }>) => async () => {
  try {
    const module = await load();
    sessionStorage.removeItem(RELOAD_FLAG);
    return { Component: module.default };
  } catch (error) {
    // After a new release an open tab may ask for page files that no longer exist: load the
    // new version once instead of showing an error (the flag prevents a reload loop).
    if (!sessionStorage.getItem(RELOAD_FLAG)) {
      sessionStorage.setItem(RELOAD_FLAG, '1');
      window.location.reload();
      return new Promise<never>(() => {});
    }
    throw error;
  }
};

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />
  },
  {
    path: '/register',
    lazy: page(() => import('./pages/Register')),
  },
  {
    path: '/',
    element: <Layout />,
    children: [
      {
        index: true,
        lazy: page(() => import('./pages/CustomerPortal')),
      },
      {
        path: 'profile',
        lazy: page(() => import('./pages/Profile')),
      },
      {
        path: 'cart',
        lazy: page(() => import('./pages/Cart')),
      },
      {
        path: 'admin',
        element: <AdminLayout />,
        children: [
          {
            index: true,
            lazy: page(() => import('./pages/AdminPortal')),
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
