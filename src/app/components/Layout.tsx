import { Outlet, Navigate, useLocation } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { Header } from './Header';
import { useTranslation } from 'react-i18next';

function SessionLoading() {
  const { t } = useTranslation();
  return (
    <div role="status" className="min-h-screen flex items-center justify-center bg-background text-muted-foreground">
      {t('common.loading')}
    </div>
  );
}

export function Layout() {
  const { isLoading } = useAuth();
  const { t } = useTranslation();

  if (isLoading) {
    return <SessionLoading />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        {t('a11y.skipToContent')}
      </a>
      <Header />
      <main id="main-content" tabIndex={-1} className="flex-1 flex flex-col overflow-hidden focus:outline-none">
        <Outlet />
      </main>
    </div>
  );
}

/** Pages that need an account (profile, cart, admin): visitors are sent to sign in. */
export function RequireAuth() {
  const { isAuthenticated, signedOut } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    // Back to this page after signing in (e.g. a link from an email), unless the reader has
    // just signed out on purpose: the next person to sign in starts on the catalogue.
    return (
      <Navigate to="/login" replace state={signedOut ? undefined : { from: location.pathname + location.search }} />
    );
  }
  return <Outlet />;
}

export function AdminLayout() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <SessionLoading />;
  }

  if (!user || user.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
