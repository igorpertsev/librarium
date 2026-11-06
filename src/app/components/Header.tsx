import { Link, useNavigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { useCart } from '../contexts/CartContext';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { ShoppingCart, User, LogOut, LayoutDashboard, Settings } from 'lucide-react';
import dragonLogo from '../../imports/dragon.png';
import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { SettingsDialog } from './SettingsDialog';

export function Header() {
  const { user, logout } = useAuth();
  const { cart } = useCart();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [settingsOpen, setSettingsOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const totalBooks = cart.reduce((sum, batch) => sum + batch.books.length, 0);

  return (
    <header className="bg-card border-b border-border sticky top-0 z-50 shadow-sm">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <img
              src={dragonLogo}
              alt="Little Dragon Logo"
              className="w-24 h-24 object-contain"
            />
            <span className="text-xl">Little Dragon</span>
          </Link>

          <nav className="flex items-center gap-4">
            {user?.role === 'admin' && (
              <Button variant="ghost" onClick={() => navigate('/admin')}>
                <LayoutDashboard className="w-4 h-4 mr-2" />
                {t('nav.admin')}
              </Button>
            )}

            <Button variant="ghost" onClick={() => navigate('/profile')}>
              <User className="w-4 h-4 mr-2" />
              {t('nav.myBooks')}
            </Button>

            <Button variant="ghost" onClick={() => navigate('/cart')} className="relative">
              <ShoppingCart className="w-4 h-4 mr-2" />
              {t('nav.cart')}
              {totalBooks > 0 && (
                <Badge className="ml-2 px-2 py-0.5 text-xs">
                  {totalBooks}
                </Badge>
              )}
            </Button>

            <Button variant="ghost" onClick={() => setSettingsOpen(true)}>
              <Settings className="w-4 h-4 mr-2" />
              {t('userMenu.settings')}
            </Button>

            <Button variant="outline" onClick={handleLogout}>
              <LogOut className="w-4 h-4 mr-2" />
              {t('nav.logout')}
            </Button>
          </nav>
        </div>
      </div>
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </header>
  );
}
