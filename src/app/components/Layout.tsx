import { Outlet, Navigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { Header } from './Header';
import { useTranslation } from 'react-i18next';

function SessionLoading() {
  const { t } = useTranslation();
  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground">
      {t('common.loading')}
    </div>
  );
}

export function Layout() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <SessionLoading />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header />
      <main className="flex-1 flex flex-col overflow-hidden">
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
