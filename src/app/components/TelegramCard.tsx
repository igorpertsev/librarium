import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Send } from 'lucide-react';
import { toast } from 'sonner';
import { usersApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { useAuth } from '../contexts/AuthContext';
import { errorMessage } from '../utils/apiErrors';
import { useLibraryRules } from '../utils/useLibraryRules';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

const CHECK_EVERY_MS = 3000;

/** Profile: get library news in Telegram too (only when the library has a bot). */
export function TelegramCard() {
  const { t } = useTranslation();
  const { user, reloadUser } = useAuth();
  const rules = useLibraryRules();
  const [waitingUntil, setWaitingUntil] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const connected = user?.telegramConnected ?? false;

  // After opening the bot, check until the chat is connected or the link expires.
  useEffect(() => {
    if (waitingUntil === null || connected) return;
    const timer = window.setInterval(() => {
      if (Date.now() > waitingUntil) setWaitingUntil(null);
      else reloadUser().catch(() => undefined);
    }, CHECK_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [waitingUntil, connected, reloadUser]);

  if (!user || !rules?.telegramBot) return null;

  const connect = async () => {
    setBusy(true);
    const result = await runAction(() => usersApi.telegramLink());
    setBusy(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    window.open(result.data.url, '_blank', 'noopener,noreferrer');
    setWaitingUntil(new Date(result.data.expires_at).getTime());
  };

  const disconnect = async () => {
    setBusy(true);
    const result = await runAction(() => usersApi.telegramUnlink());
    setBusy(false);
    if (result.ok) {
      toast.success(t('telegram.disconnected'));
      await reloadUser().catch(() => undefined);
    } else {
      toast.error(errorMessage(t, result.error));
    }
  };

  return (
    <Card data-testid="telegram">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Send className="w-5 h-5" aria-hidden="true" />
          {t('telegram.title')}
        </CardTitle>
        <CardDescription>
          {connected ? t('telegram.connected', { bot: rules.telegramBot }) : t('telegram.description')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {connected ? (
          <Button variant="outline" onClick={disconnect} disabled={busy}>
            {t('telegram.disconnect')}
          </Button>
        ) : (
          <>
            <Button onClick={connect} disabled={busy}>
              {t('telegram.connect')}
            </Button>
            {waitingUntil !== null && (
              <p role="status" className="text-sm text-muted-foreground">
                {t('telegram.waiting')}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
