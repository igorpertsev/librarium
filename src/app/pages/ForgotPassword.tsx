import { useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { MailCheck } from 'lucide-react';
import { authApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { AuthCard } from '../components/AuthCard';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { errorMessage } from '../utils/apiErrors';

export default function ForgotPassword() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    const result = await runAction(() => authApi.forgotPassword({ email }));
    setSubmitting(false);
    if (result.ok) setSentTo(email);
    else setError(errorMessage(t, result.error));
  };

  const backToSignIn = (
    <Link to="/login" className="text-sm text-primary underline underline-offset-4">
      {t('auth.backToSignIn')}
    </Link>
  );

  if (sentTo) {
    return (
      <AuthCard title={t('auth.forgotTitle')} footer={backToSignIn}>
        <div role="status" className="flex flex-col items-center gap-3 text-center">
          <MailCheck className="w-10 h-10 text-primary" aria-hidden="true" />
          <p className="text-sm">{t('auth.resetLinkSent', { email: sentTo })}</p>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t('auth.forgotTitle')} description={t('auth.forgotDescription')} footer={backToSignIn}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">{t('auth.email')}</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="your@email.com"
            autoComplete="email"
            required
          />
        </div>
        {error && (
          <div role="alert" className="text-sm text-destructive dark:text-red-300 bg-destructive/10 p-3 rounded-md">
            {error}
          </div>
        )}
        <Button type="submit" className="w-full" disabled={submitting}>
          {t('auth.sendResetLink')}
        </Button>
      </form>
    </AuthCard>
  );
}
