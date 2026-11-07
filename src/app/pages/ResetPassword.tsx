import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { authApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { AuthCard } from '../components/AuthCard';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { errorMessage } from '../utils/apiErrors';

const MIN_PASSWORD_LENGTH = 8;

/** The token from the emailed link (#token=...). */
function tokenFromUrl(): string {
  return new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '';
}

export default function ResetPassword() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [token] = useState(tokenFromUrl);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [linkInvalid, setLinkInvalid] = useState(!token);
  const [submitting, setSubmitting] = useState(false);

  // Keep the token out of the address bar and browser history once it has been read.
  useEffect(() => {
    if (location.hash) navigate(location.pathname, { replace: true });
  }, [location.hash, location.pathname, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password.length < MIN_PASSWORD_LENGTH) { setError(t('auth.passwordLength')); return; }
    if (password !== confirmPassword) { setError(t('auth.passwordMismatch')); return; }
    setSubmitting(true);
    const result = await runAction(() => authApi.resetPassword({ token, new_password: password }));
    setSubmitting(false);
    if (result.ok) {
      toast.success(t('auth.passwordResetDone'));
      navigate('/login', { replace: true });
    } else if (result.error.code === 'INVALID_RESET_TOKEN') {
      setLinkInvalid(true);
    } else {
      setError(errorMessage(t, result.error));
    }
  };

  const backToSignIn = (
    <Link to="/login" className="text-sm text-primary underline underline-offset-4">
      {t('auth.backToSignIn')}
    </Link>
  );

  if (linkInvalid) {
    return (
      <AuthCard title={t('auth.resetTitle')} footer={backToSignIn}>
        <div role="alert" className="space-y-4 text-center">
          <p className="text-sm text-destructive dark:text-red-300 bg-destructive/10 p-3 rounded-md">{t('auth.invalidResetLink')}</p>
          <Button asChild className="w-full">
            <Link to="/forgot-password">{t('auth.requestNewLink')}</Link>
          </Button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t('auth.resetTitle')} description={t('auth.resetDescription')} footer={backToSignIn}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="password">{t('auth.newPassword')}</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('auth.passwordPlaceholder')}
            autoComplete="new-password"
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirmPassword">{t('auth.confirmPassword')}</Label>
          <Input
            id="confirmPassword"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder={t('auth.confirmPasswordPlaceholder')}
            autoComplete="new-password"
            required
          />
        </div>
        {error && (
          <div role="alert" className="text-sm text-destructive dark:text-red-300 bg-destructive/10 p-3 rounded-md">
            {error}
          </div>
        )}
        <Button type="submit" className="w-full" disabled={submitting}>
          {t('auth.setNewPassword')}
        </Button>
      </form>
    </AuthCard>
  );
}
