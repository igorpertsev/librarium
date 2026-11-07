import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { usersApi } from '../../api/endpoints';
import { runAction, type ActionResult } from '../../api/errors';
import type { ChildDto } from '../../api/types';
import { useAuth } from './AuthContext';

interface FamilyContextType {
  children: ChildDto[];
  addChild: (name: string, birthYear: number | null) => Promise<ActionResult>;
  removeChild: (childId: string) => Promise<ActionResult>;
}

const FamilyContext = createContext<FamilyContextType | undefined>(undefined);

/** Child profiles of a family account. */
export function FamilyProvider({ children: content }: { children: ReactNode }) {
  const { user } = useAuth();
  const [children, setChildren] = useState<ChildDto[]>([]);

  const load = useCallback(async () => {
    setChildren(await usersApi.children());
  }, []);

  useEffect(() => {
    if (user) load().catch(() => setChildren([]));
    else setChildren([]);
  }, [user, load]);

  const addChild = (name: string, birthYear: number | null) =>
    runAction(async () => {
      await usersApi.addChild({ name, birth_year: birthYear });
      await load();
    });
  const removeChild = (childId: string) =>
    runAction(async () => {
      await usersApi.removeChild(childId);
      await load();
    });

  return <FamilyContext.Provider value={{ children, addChild, removeChild }}>{content}</FamilyContext.Provider>;
}

export function useFamily() {
  const context = useContext(FamilyContext);
  if (!context) throw new Error('useFamily must be used within FamilyProvider');
  return context;
}
