import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from 'react';

interface CatalogContextType {
  /** Incremented whenever book availability may have changed (orders, 409 conflicts, admin edits). */
  version: number;
  invalidateCatalog: () => void;
}

const CatalogContext = createContext<CatalogContextType | undefined>(undefined);

export function CatalogProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0);
  const invalidateCatalog = useCallback(() => setVersion((v) => v + 1), []);
  const value = useMemo(() => ({ version, invalidateCatalog }), [version, invalidateCatalog]);
  return <CatalogContext.Provider value={value}>{children}</CatalogContext.Provider>;
}

export function useCatalog() {
  const context = useContext(CatalogContext);
  if (!context) throw new Error('useCatalog must be used within CatalogProvider');
  return context;
}
