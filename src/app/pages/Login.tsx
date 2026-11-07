import { useState } from 'react';
import { useNavigate, Link, Navigate, useLocation } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader } from '../components/ui/card';
import dragonLogo from '../../imports/dragon.webp';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { errorMessage } from '../utils/apiErrors';

export default function Login() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // Two-step sign-in: the password was right; now a code from the app.
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const { login, loginWithCode, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // Only paths on this site: never an absolute or protocol-relative address.
  const requested = (location.state as { from?: unknown } | null)?.from;
  const returnTo =
    typeof requested === 'string' && requested.startsWith('/') && !requested.startsWith('//') ? requested : '/';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    const result = mfaToken ? await loginWithCode(mfaToken, code) : await login(email, password);
    setSubmitting(false);
    if (result.ok) {
      toast.success(t('auth.loginSuccess'));
      navigate(returnTo, { replace: true });
    } else if (result.error.code === 'MFA_REQUIRED' && typeof result.error.details?.mfa_token === 'string') {
      setMfaToken(result.error.details.mfa_token);
      setCode('');
    } else if (result.error.code === 'MFA_TOKEN_INVALID') {
      setMfaToken(null); // took too long: start again with the password
      setError(errorMessage(t, result.error));
    } else {
      setError(errorMessage(t, result.error));
    }
  };

  if (!isLoading && isAuthenticated) {
    return <Navigate to={returnTo} replace />;
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <img
              src={dragonLogo}
              alt={t('brand.logoAlt')}
              className="w-40 h-40 object-contain"
            />
          </div>
          <h1 data-slot="card-title" className="leading-none text-base">{t('home.title')}</h1>
          <CardDescription>{t('auth.signIn')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {mfaToken ? (
              <div className="space-y-2">
                <Label htmlFor="mfa-code">{t('mfa.codeLabel')}</Label>
                <Input
                  id="mfa-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  autoComplete="one-time-code"
                  inputMode="text"
                  autoFocus
                  required
                />
                <p className="text-xs text-muted-foreground">{t('mfa.codeHint')}</p>
              </div>
            ) : (
            <>
            <div className="space-y-2">
              <Label htmlFor="email">{t('auth.email')}</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                required
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <Label htmlFor="password">{t('auth.password')}</Label>
                <Link to="/forgot-password" className="text-sm text-primary underline underline-offset-4">
                  {t('auth.forgotPassword')}
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            </>
            )}
            {error && (
              <div role="alert" className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" disabled={submitting}>
              {mfaToken ? t('mfa.verify') : t('auth.signIn')}
            </Button>
            {mfaToken && (
              <Button type="button" variant="ghost" className="w-full" onClick={() => setMfaToken(null)}>
                {t('mfa.back')}
              </Button>
            )}
          </form>
        </CardContent>
        <CardFooter className="flex flex-col items-center gap-2">
          <p className="text-sm text-muted-foreground">
            {t('auth.noAccount')}{' '}
            <Link to="/register" className="text-primary underline underline-offset-4">
              {t('auth.signUp')}
            </Link>
          </p>
          <p className="text-sm text-muted-foreground text-center">
            <Link to="/" className="text-primary underline underline-offset-4">{t('auth.browseCatalogue')}</Link>
          </p>
        </CardFooter>
      </Card>
    </main>
  );
}
