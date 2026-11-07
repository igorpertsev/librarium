import { Link, useNavigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { useCart } from '../contexts/CartContext';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { NotificationBell } from './NotificationBell';
import { ShoppingCart, User, LogOut, LogIn, UserPlus, LayoutDashboard, Settings, Menu } from 'lucide-react';
import dragonLogo from '../../imports/dragon.webp';
import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { SettingsDialog } from './SettingsDialog';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from './ui/sheet';
import { isStaff } from '../utils/roles';

export function Header() {
  const { user, logout } = useAuth();
  const { cart } = useCart();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const totalBooks = cart.reduce((sum, batch) => sum + batch.books.length, 0);

  // Mobile menu: close the sheet before navigating.
  const go = (path: string) => {
    setMenuOpen(false);
    navigate(path);
  };
  const mobileItems = [
    ...(isStaff(user) ? [{ label: t('nav.admin'), icon: LayoutDashboard, onClick: () => go('/admin') }] : []),
    ...(user
      ? [
          { label: t('nav.myBooks'), icon: User, onClick: () => go('/profile') },
          { label: t('nav.cart'), icon: ShoppingCart, onClick: () => go('/cart'), badge: totalBooks },
        ]
      : [
          { label: t('nav.signIn'), icon: LogIn, onClick: () => go('/login') },
          { label: t('nav.register'), icon: UserPlus, onClick: () => go('/register') },
        ]),
    {
      label: t('userMenu.settings'),
      icon: Settings,
      onClick: () => {
        setMenuOpen(false);
        setSettingsOpen(true);
      },
    },
  ];

  return (
    <header className="bg-card border-b border-border sticky top-0 z-50 shadow-sm">
      <div className="container mx-auto px-4 py-2 md:py-4">
        <div className="flex items-center justify-between gap-2">
          <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <img
              src={dragonLogo}
              alt={t('brand.logoAlt')}
              className="w-12 h-12 md:w-24 md:h-24 object-contain"
            />
            <span className="text-lg md:text-xl">Little Dragon</span>
          </Link>

          <nav className="hidden md:flex items-center gap-4">
            {isStaff(user) && (
              <Button variant="ghost" onClick={() => navigate('/admin')}>
                <LayoutDashboard className="w-4 h-4 mr-2" />
                {t('nav.admin')}
              </Button>
            )}

            {user && (
              <>
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
                <NotificationBell />
              </>
            )}

            <Button variant="ghost" onClick={() => setSettingsOpen(true)}>
              <Settings className="w-4 h-4 mr-2" />
              {t('userMenu.settings')}
            </Button>

            {user ? (
              <Button variant="outline" onClick={handleLogout}>
                <LogOut className="w-4 h-4 mr-2" />
                {t('nav.logout')}
              </Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => navigate('/register')}>
                  <UserPlus className="w-4 h-4 mr-2" />
                  {t('nav.register')}
                </Button>
                <Button onClick={() => navigate('/login')}>
                  <LogIn className="w-4 h-4 mr-2" />
                  {t('nav.signIn')}
                </Button>
              </>
            )}
          </nav>

          {/* Small screens: cart shortcut + menu */}
          <div className="flex md:hidden items-center gap-1">
            {user && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => go('/cart')}
                aria-label={t('nav.cart')}
                className="relative"
              >
                <ShoppingCart className="w-5 h-5" />
                {totalBooks > 0 && (
                  <Badge className="absolute -top-1 -right-1 px-1.5 py-0 text-[10px]">{totalBooks}</Badge>
                )}
              </Button>
            )}
            {user && <NotificationBell compact />}
            <Button variant="ghost" size="icon" onClick={() => setMenuOpen(true)} aria-label={t('nav.openMenu')}>
              <Menu className="w-5 h-5" />
            </Button>
          </div>
        </div>
      </div>

      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="right" className="w-72">
          <SheetHeader>
            <SheetTitle>{t('nav.menu')}</SheetTitle>
            <SheetDescription>{user?.email}</SheetDescription>
          </SheetHeader>
          <nav className="flex flex-col gap-1 px-4">
            {mobileItems.map(({ label, icon: Icon, onClick, badge }) => (
              <Button key={label} variant="ghost" className="justify-start" onClick={onClick}>
                <Icon className="w-4 h-4 mr-2" />
                {label}
                {badge ? <Badge className="ml-auto px-2 py-0.5 text-xs">{badge}</Badge> : null}
              </Button>
            ))}
            {user && (
              <Button
                variant="outline"
                className="justify-start mt-4"
                onClick={() => {
                  setMenuOpen(false);
                  void handleLogout();
                }}
              >
                <LogOut className="w-4 h-4 mr-2" />
                {t('nav.logout')}
              </Button>
            )}
          </nav>
        </SheetContent>
      </Sheet>

      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </header>
  );
}
