import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { API_URL } from '../../api/client';
import { authApi } from '../../api/endpoints';
import { Button } from './ui/button';

const LABELS: Record<string, string> = { google: 'social.google', apple: 'social.apple' };

/** "Continue with Google / Apple", for the providers the library has set up. */
export function SocialSignIn({ returnTo = '/' }: { returnTo?: string }) {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<string[]>([]);

  useEffect(() => {
    authApi.oauthProviders().then((r) => setProviders(r.providers), () => setProviders([]));
  }, []);

  if (providers.length === 0) return null;
  return (
    <div className="space-y-2" data-testid="social-sign-in">
      <div className="flex items-center gap-2 text-xs text-muted-foreground" aria-hidden="true">
        <span className="h-px flex-1 bg-border" />
        {t('social.or')}
        <span className="h-px flex-1 bg-border" />
      </div>
      {providers.map((provider) => (
        <Button key={provider} type="button" variant="outline" className="w-full" asChild>
          <a href={`${API_URL}/auth/oauth/${provider}/start?next=${encodeURIComponent(returnTo)}`}>
            {t(LABELS[provider] ?? 'social.other', { provider })}
          </a>
        </Button>
      ))}
    </div>
  );
}
