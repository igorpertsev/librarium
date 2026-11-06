import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { UiLanguage, User, UserContacts } from '../types';
import { refreshSession, setAccessToken, setAuthListeners } from '../../api/client';
import { adminApi, authApi, fetchAllPages, usersApi } from '../../api/endpoints';
import { ActionResult, runAction } from '../../api/errors';
import { contactsToDto, userFromDto } from '../../api/mappers';
import type { TokenResponseDto } from '../../api/types';

interface AuthContextType {
  user: User | null;
  /** Admin only: all users with their active loans. */
  users: User[];
  /** True while the session is being restored from the refresh cookie on page load. */
  isLoading: boolean;
  login: (email: string, password: string) => Promise<ActionResult>;
  register: (name: string, email: string, password: string, contacts: UserContacts) => Promise<ActionResult>;
  updateUser: (name: string, email: string, contacts: UserContacts) => Promise<ActionResult>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<ActionResult>;
  updateUserRole: (userId: string, role: 'customer' | 'admin') => Promise<ActionResult>;
  refreshUsers: () => Promise<void>;
  /** Switch the interface language; saved on the account when signed in. */
  setLanguage: (language: UiLanguage) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const currentLanguage = (language: string): UiLanguage | null =>
  language.startsWith('ru') ? 'ru' : language.startsWith('en') ? 'en' : null;

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { i18n } = useTranslation();

  // The language saved on the account wins over this browser's choice (it follows the user
  // to other devices).
  const savedLanguage = user?.preferredLanguage;
  useEffect(() => {
    if (savedLanguage && savedLanguage !== i18n.language) {
      i18n.changeLanguage(savedLanguage);
      localStorage.setItem('language', savedLanguage);
    }
  }, [savedLanguage, i18n]);

  const applyTokens = useCallback((response: TokenResponseDto) => {
    setAccessToken(response.access_token);
    setUser(userFromDto(response.user));
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setUsers([]);
  }, []);

  useEffect(() => {
    setAuthListeners({
      onSessionExpired: clearSession,
      onTokenRefreshed: (response) => setUser(userFromDto(response.user)),
    });
    // Restore the session from the HttpOnly refresh cookie (if any).
    refreshSession()
      .catch(() => null)
      .finally(() => setIsLoading(false));
    return () => setAuthListeners({});
  }, [clearSession]);

  const refreshUsers = useCallback(async () => {
    const all = await fetchAllPages((page, page_size) => adminApi.listUsers({ page, page_size }));
    setUsers(all.map(userFromDto));
  }, []);

  useEffect(() => {
    if (user?.role === 'admin') {
      refreshUsers().catch(() => setUsers([]));
    } else {
      setUsers([]);
    }
  }, [user?.id, user?.role, refreshUsers]);

  const login = (email: string, password: string) =>
    runAction(async () => {
      applyTokens(await authApi.login({ email, password }));
    });

  const register = (name: string, email: string, password: string, contacts: UserContacts) =>
    runAction(async () => {
      applyTokens(
        await authApi.register({
          email,
          password,
          full_name: name,
          ...contactsToDto(contacts),
          preferred_language: currentLanguage(i18n.language),
        }),
      );
    });

  const updateUser = (name: string, email: string, contacts: UserContacts) =>
    runAction(async () => {
      const updated = await usersApi.updateMe({
        full_name: name,
        email,
        ...contactsToDto(contacts),
      });
      setUser(userFromDto(updated));
    });

  /** Switch the interface language and, when signed in, save it on the account. */
  const setLanguage = async (language: UiLanguage) => {
    await i18n.changeLanguage(language);
    localStorage.setItem('language', language);
    if (user && user.preferredLanguage !== language) {
      try {
        setUser(userFromDto(await usersApi.updateMe({ preferred_language: language })));
      } catch {
        // Not critical: the browser keeps the choice; the account is updated next time.
      }
    }
  };

  const changePassword = (currentPassword: string, newPassword: string) =>
    runAction(async () => {
      // Other sessions are signed out by the server; this one receives fresh tokens.
      applyTokens(
        await authApi.changePassword({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      );
    });

  const updateUserRole = (userId: string, role: 'customer' | 'admin') =>
    runAction(async () => {
      const updated = await adminApi.updateUser(userId, { role });
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...userFromDto(updated), borrowedBooks: u.borrowedBooks } : u)),
      );
      if (user?.id === userId) setUser((prev) => (prev ? { ...prev, role } : prev));
    });

  const logout = () => {
    // Revoke the refresh token server-side; local state is cleared immediately either way.
    authApi.logout().catch(() => undefined);
    clearSession();
  };

  return (
    <AuthContext.Provider value={{
      user,
      users,
      isLoading,
      login,
      register,
      updateUser,
      changePassword,
      updateUserRole,
      refreshUsers,
      setLanguage,
      logout,
      isAuthenticated: !!user
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

export type { AuthContextType };
