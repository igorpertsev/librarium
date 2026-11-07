import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { KeyRound, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { usersApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { PasskeyDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { createPasskey, passkeysSupported } from '../utils/passkeys';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';

/** Profile: passkeys (Face ID, Touch ID, Windows Hello, a phone) to sign in without a password. */
export function PasskeysCard() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const [passkeys, setPasskeys] = useState<PasskeyDto[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setPasskeys(await usersApi.listPasskeys().catch(() => []));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!passkeysSupported() || passkeys === null) return null;

  const add = async () => {
    setBusy(true);
    const result = await runAction(async () => {
      const { options, state } = await usersApi.passkeyOptions(password);
      const credential = await createPasskey(options);
      return usersApi.addPasskey({ state, credential, name: name.trim() || t('passkeys.defaultName') });
    });
    setBusy(false);
    if (!result.ok) {
      if (result.error.code !== 'PASSKEY_CANCELLED') toast.error(errorMessage(t, result.error));
      return;
    }
    toast.success(t('passkeys.added'));
    setAdding(false);
    setPassword('');
    setName('');
    await load();
  };

  const remove = async (passkey: PasskeyDto) => {
    const result = await runAction(() => usersApi.removePasskey(passkey.id));
    if (result.ok) {
      toast.success(t('passkeys.removed'));
      await load();
    } else toast.error(errorMessage(t, result.error));
  };

  return (
    <Card data-testid="passkeys">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="w-5 h-5" aria-hidden="true" />
          {t('passkeys.title')}
        </CardTitle>
        <CardDescription>{t('passkeys.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {passkeys.length > 0 && (
          <ul className="space-y-1" aria-label={t('passkeys.title')}>
            {passkeys.map((passkey) => (
              <li key={passkey.id} className="flex items-center justify-between gap-2 text-sm">
                <span>
                  {passkey.name}{' '}
                  <span className="text-muted-foreground">
                    · {passkey.last_used_at ? t('passkeys.lastUsed', { date: fmt.date(passkey.last_used_at) }) : t('passkeys.neverUsed')}
                  </span>
                </span>
                <Button size="sm" variant="ghost" onClick={() => remove(passkey)} aria-label={t('passkeys.removeNamed', { name: passkey.name })}>
                  <Trash2 className="w-4 h-4" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {adding ? (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void add();
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="passkey-name">{t('passkeys.name')}</Label>
              <Input id="passkey-name" maxLength={100} placeholder={t('passkeys.namePlaceholder')} value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="passkey-password">{t('passkeys.password')}</Label>
              <Input id="passkey-password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || !password}>{t('passkeys.create')}</Button>
              <Button type="button" variant="ghost" onClick={() => setAdding(false)}>{t('common.cancel')}</Button>
            </div>
          </form>
        ) : (
          <Button variant="outline" onClick={() => setAdding(true)}>{t('passkeys.add')}</Button>
        )}
      </CardContent>
    </Card>
  );
}
