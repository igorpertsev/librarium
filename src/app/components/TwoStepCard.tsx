import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { usersApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { useAuth } from '../contexts/AuthContext';
import { errorMessage } from '../utils/apiErrors';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';

type Step = 'idle' | 'password' | 'scan' | 'codes' | 'disable';

/** Profile: turn two-step sign-in (authenticator app) on or off. */
export function TwoStepCard() {
  const { t } = useTranslation();
  const { user, reloadUser } = useAuth();
  const [step, setStep] = useState<Step>('idle');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!setup) return;
    let active = true;
    import('qrcode')
      .then((QRCode) => QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 192 }))
      .then((url) => active && setQr(url), () => active && setQr(null));
    return () => {
      active = false;
    };
  }, [setup]);

  if (!user) return null;

  const run = async <T,>(action: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    const result = await runAction(action);
    setBusy(false);
    if (result.ok) return result.data;
    toast.error(errorMessage(t, result.error));
    return null;
  };

  const reset = () => {
    setStep('idle');
    setPassword('');
    setCode('');
    setSetup(null);
    setQr(null);
  };

  const start = async () => {
    const result = await run(() => usersApi.mfaSetup(password));
    if (result) {
      setSetup(result);
      setPassword('');
      setStep('scan');
    }
  };

  const confirm = async () => {
    const result = await run(() => usersApi.mfaEnable(code.trim()));
    if (result) {
      setCodes(result.recovery_codes);
      setStep('codes');
      await reloadUser().catch(() => undefined);
    }
  };

  const turnOff = async () => {
    const ok = await run(() => usersApi.mfaDisable(password));
    if (ok !== null) {
      toast.success(t('mfa.disabled'));
      reset();
      await reloadUser().catch(() => undefined);
    }
  };

  const downloadCodes = () => {
    const blob = new Blob([`${t('mfa.codesFileTitle')}\n\n${codes.join('\n')}\n`], { type: 'text/plain' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'little-dragon-recovery-codes.txt';
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <Card data-testid="two-step">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5" aria-hidden="true" />
          {t('mfa.title')}
        </CardTitle>
        <CardDescription>{user.mfaEnabled ? t('mfa.on') : t('mfa.off')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {step === 'idle' && (
          <Button variant="outline" onClick={() => setStep(user.mfaEnabled ? 'disable' : 'password')}>
            {user.mfaEnabled ? t('mfa.turnOff') : t('mfa.turnOn')}
          </Button>
        )}

        {(step === 'password' || step === 'disable') && (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void (step === 'password' ? start() : turnOff());
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="mfa-password">{t('mfa.password')}</Label>
              <Input
                id="mfa-password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || !password}>
                {step === 'password' ? t('mfa.continue') : t('mfa.turnOff')}
              </Button>
              <Button type="button" variant="ghost" onClick={reset}>
                {t('common.cancel')}
              </Button>
            </div>
          </form>
        )}

        {step === 'scan' && setup && (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void confirm();
            }}
          >
            <p className="text-sm">{t('mfa.scan')}</p>
            {qr && <img src={qr} alt={t('mfa.qrAlt')} className="w-48 h-48 rounded bg-white p-1" />}
            <p className="text-xs text-muted-foreground break-all">
              {t('mfa.manual')} <code className="font-mono">{setup.secret}</code>
            </p>
            <div className="space-y-2">
              <Label htmlFor="mfa-first-code">{t('mfa.firstCode')}</Label>
              <Input
                id="mfa-first-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || code.trim().length < 6}>
                {t('mfa.turnOn')}
              </Button>
              <Button type="button" variant="ghost" onClick={reset}>
                {t('common.cancel')}
              </Button>
            </div>
          </form>
        )}

        {step === 'codes' && (
          <div className="space-y-3">
            <p className="text-sm font-medium">{t('mfa.enabled')}</p>
            <p className="text-sm">{t('mfa.codesHint')}</p>
            <ul className="grid grid-cols-2 gap-1 font-mono text-sm" aria-label={t('mfa.codesLabel')}>
              {codes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <div className="flex gap-2">
              <Button variant="outline" onClick={downloadCodes}>
                {t('mfa.download')}
              </Button>
              <Button onClick={reset}>{t('mfa.done')}</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
