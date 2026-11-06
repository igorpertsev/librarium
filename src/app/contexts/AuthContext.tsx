import React, { createContext, useContext, useState, ReactNode } from 'react';
import { User, UserContacts } from '../types';

interface UserWithPassword extends User {
  password: string;
}

interface AuthContextType {
  user: User | null;
  users: User[];
  login: (email: string, password: string) => Promise<boolean>;
  register: (name: string, email: string, password: string, contacts: UserContacts) => Promise<boolean>;
  updateUser: (name: string, email: string, contacts: UserContacts) => Promise<boolean>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<boolean>;
  updateUserRole: (userId: string, role: 'customer' | 'admin') => boolean;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Import mock books for borrowed books data
import { mockBooks } from '../data/mockBooks';

const mockUsersWithPasswords: UserWithPassword[] = [
  {
    id: '1',
    name: 'John Customer',
    email: 'customer@library.com',
    role: 'customer',
    borrowedBooks: [
      {
        bookId: '1',
        book: mockBooks[0],
        borrowedDate: '2026-05-10',
        returnDate: '2026-06-10'
      },
      {
        bookId: '2',
        book: mockBooks[1],
        borrowedDate: '2026-05-15',
        returnDate: '2026-06-15'
      }
    ],
    contacts: { whatsapp: '+1234567890', telegram: '@johncustomer', preferred: 'whatsapp' },
    password: 'password'
  },
  {
    id: '2',
    name: 'Admin User',
    email: 'admin@library.com',
    role: 'admin',
    borrowedBooks: [],
    contacts: { phone: '+9876543210' },
    password: 'password'
  }
];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [usersWithPasswords, setUsersWithPasswords] = useState<UserWithPassword[]>(mockUsersWithPasswords);

  const users = usersWithPasswords.map(({ password, ...user }) => user);

  const login = async (email: string, password: string): Promise<boolean> => {
    const foundUser = usersWithPasswords.find(u => u.email === email);
    if (foundUser && password === foundUser.password) {
      const { password: _, ...userWithoutPassword } = foundUser;
      setUser(userWithoutPassword);
      return true;
    }
    return false;
  };

  const register = async (name: string, email: string, password: string, contacts: UserContacts): Promise<boolean> => {
    const existingUser = usersWithPasswords.find(u => u.email === email);
    if (existingUser) return false;

    const newUser: UserWithPassword = {
      id: `user-${Date.now()}`,
      name,
      email,
      role: 'customer',
      borrowedBooks: [],
      contacts,
      password
    };

    setUsersWithPasswords([...usersWithPasswords, newUser]);
    const { password: _, ...userWithoutPassword } = newUser;
    setUser(userWithoutPassword);
    return true;
  };

  const updateUser = async (name: string, email: string, contacts: UserContacts): Promise<boolean> => {
    if (!user) return false;

    const existingUser = usersWithPasswords.find(u => u.email === email && u.id !== user.id);
    if (existingUser) return false;

    const updatedUser = { ...user, name, email, contacts };
    setUser(updatedUser);
    setUsersWithPasswords(usersWithPasswords.map(u =>
      u.id === user.id ? { ...u, name, email, contacts } : u
    ));
    return true;
  };

  const changePassword = async (currentPassword: string, newPassword: string): Promise<boolean> => {
    if (!user) return false;

    const userWithPassword = usersWithPasswords.find(u => u.id === user.id);
    if (!userWithPassword || userWithPassword.password !== currentPassword) {
      return false;
    }

    setUsersWithPasswords(usersWithPasswords.map(u =>
      u.id === user.id ? { ...u, password: newPassword } : u
    ));
    return true;
  };

  const updateUserRole = (userId: string, role: 'customer' | 'admin'): boolean => {
    const targetUser = usersWithPasswords.find(u => u.id === userId);
    if (!targetUser) return false;

    setUsersWithPasswords(usersWithPasswords.map(u =>
      u.id === userId ? { ...u, role } : u
    ));

    // Update current user if they're the one being modified
    if (user?.id === userId) {
      setUser({ ...user, role });
    }

    return true;
  };

  const logout = () => {
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{
      user,
      users,
      login,
      register,
      updateUser,
      changePassword,
      updateUserRole,
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
