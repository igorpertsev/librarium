import type { User } from '../types';

export type Role = User['role'];

/** Librarians and administrators use the admin portal. */
export const isStaff = (user: Pick<User, 'role'> | null | undefined): boolean =>
  user?.role === 'admin' || user?.role === 'librarian';

/** Users, settings, pickup points and the activity log are for administrators. */
export const isAdmin = (user: Pick<User, 'role'> | null | undefined): boolean => user?.role === 'admin';
