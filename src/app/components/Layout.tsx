import { Outlet, Navigate } from 'react-router';
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
  const { isAuthenticated, isLoading } = useAuth();
  const { t } = useTranslation();

  if (isLoading) {
    return <SessionLoading />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
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
