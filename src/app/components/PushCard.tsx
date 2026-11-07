import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BellRing } from 'lucide-react';
import { toast } from 'sonner';
import { usersApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { useAuth } from '../contexts/AuthContext';
import { errorMessage } from '../utils/apiErrors';
import { base64UrlToBytes, pushSupported } from '../utils/push';
import { useLibraryRules } from '../utils/useLibraryRules';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

/** Profile: the library's news as notifications on this device (Web Push). Shown only where it
 * can work: the library has push keys and the app runs with its service worker (installed app
 * or production site). */
export function PushCard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const rules = useLibraryRules();
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(() => pushSupported() && Notification.permission === 'denied');

  useEffect(() => {
    if (!pushSupported()) return;
    let active = true;
    navigator.serviceWorker
      .getRegistration()
      .then(async (found) => {
        if (!active || !found) return;
        setRegistration(found);
        setSubscribed((await found.pushManager.getSubscription()) !== null);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  if (!user || !rules?.webPushKey || !registration) return null;
  const key = rules.webPushKey;

  const turnOn = async () => {
    setBusy(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setBlocked(permission === 'denied');
        toast.error(t('push.notAllowed'));
        return;
      }
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: base64UrlToBytes(key),
      });
      const json = subscription.toJSON();
      const result = await runAction(() =>
        usersApi.pushSubscribe({
          endpoint: subscription.endpoint,
          keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
        }),
      );
      if (result.ok) {
        setSubscribed(true);
        toast.success(t('push.on'));
      } else {
        await subscription.unsubscribe().catch(() => undefined);
        toast.error(errorMessage(t, result.error));
      }
    } catch {
      toast.error(t('push.failed'));
    } finally {
      setBusy(false);
    }
  };

  const turnOff = async () => {
    setBusy(true);
    try {
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        await runAction(() => usersApi.pushUnsubscribe(subscription.endpoint));
        await subscription.unsubscribe();
      }
      setSubscribed(false);
      toast.success(t('push.off'));
    } catch {
      toast.error(t('push.failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card data-testid="push">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BellRing className="w-5 h-5" aria-hidden="true" />
          {t('push.title')}
        </CardTitle>
        <CardDescription>{subscribed ? t('push.enabled') : t('push.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {subscribed ? (
          <Button variant="outline" onClick={turnOff} disabled={busy}>
            {t('push.turnOff')}
          </Button>
        ) : (
          <Button onClick={turnOn} disabled={busy || blocked}>
            {t('push.turnOn')}
          </Button>
        )}
        {blocked && !subscribed && (
          <p role="status" className="text-sm text-muted-foreground">
            {t('push.blocked')}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
