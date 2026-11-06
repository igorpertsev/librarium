import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router';

/** Sends a visitor to sign in, and back to this page afterwards. */
export function useSignInFirst(): () => void {
  const navigate = useNavigate();
  const location = useLocation();
  return useCallback(
    () => navigate('/login', { state: { from: location.pathname + location.search } }),
    [navigate, location.pathname, location.search],
  );
}
