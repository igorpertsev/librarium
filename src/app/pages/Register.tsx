import { useState } from 'react';
import { useNavigate, Link, Navigate } from 'react-router';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader } from '../components/ui/card';
import dragonLogo from '../../imports/dragon.png';
import { useTranslation } from 'react-i18next';
import { PreferredContact } from '../types';
import { Star } from 'lucide-react';
import { errorMessage } from '../utils/apiErrors';

const MIN_PASSWORD_LENGTH = 8;

const CONTACT_FIELDS: { key: PreferredContact; labelKey: string; placeholder: string; type: string }[] = [
  { key: 'whatsapp',  labelKey: 'auth.whatsapp',  placeholder: '+1 234 567 8900', type: 'text' },
  { key: 'telegram',  labelKey: 'auth.telegram',  placeholder: '@username',       type: 'text' },
  { key: 'instagram', labelKey: 'auth.instagram', placeholder: '@handle',         type: 'text' },
  { key: 'phone',     labelKey: 'auth.phone',     placeholder: '+1 234 567 8900', type: 'tel'  },
];

export default function Register() {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [contactValues, setContactValues] = useState<Record<PreferredContact, string>>({
    whatsapp: '', telegram: '', instagram: '', phone: '',
  });
  const [preferred, setPreferred] = useState<PreferredContact | ''>('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { register, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();

  const setContact = (key: PreferredContact, value: string) => {
    setContactValues(prev => ({ ...prev, [key]: value }));
    if (!value.trim() && preferred === key) setPreferred('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.trim()) { setError(t('auth.nameRequired')); return; }
    if (password.length < MIN_PASSWORD_LENGTH) { setError(t('auth.passwordLength')); return; }
    if (password !== confirmPassword) { setError(t('auth.passwordMismatch')); return; }

    const contacts = {
      whatsapp:  contactValues.whatsapp.trim()  || undefined,
      telegram:  contactValues.telegram.trim()  || undefined,
      instagram: contactValues.instagram.trim() || undefined,
      phone:     contactValues.phone.trim()     || undefined,
      preferred: preferred || undefined,
    };

    if (!contacts.whatsapp && !contacts.telegram && !contacts.instagram && !contacts.phone) {
      setError(t('auth.contactRequired'));
      return;
    }

    setSubmitting(true);
    const result = await register(name, email, password, contacts);
    setSubmitting(false);
    if (result.ok) navigate('/');
    else setError(errorMessage(t, result.error));
  };

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <img src={dragonLogo} alt={t('brand.logoAlt')} className="w-40 h-40 object-contain" />
          </div>
          <h1 data-slot="card-title" className="leading-none text-base">{t('auth.createAccount')}</h1>
          <CardDescription>{t('auth.joinLibrary')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">{t('auth.name')}</Label>
              <Input id="name" type="text" value={name} onChange={e => setName(e.target.value)} placeholder="John Doe" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">{t('auth.email')}</Label>
              <Input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="your@email.com" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">{t('auth.password')}</Label>
              <Input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder={t('auth.passwordPlaceholder')} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">{t('auth.confirmPassword')}</Label>
              <Input id="confirmPassword" type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder={t('auth.confirmPasswordPlaceholder')} required />
            </div>

            <div className="space-y-3 pt-2">
              <div>
                <p className="text-sm font-medium">{t('auth.contactInfo')} <span className="text-muted-foreground font-normal text-xs">({t('auth.atLeastOne')})</span></p>
                <p className="text-xs text-muted-foreground mt-0.5">{t('auth.starToMarkPreferred')}</p>
              </div>
              {CONTACT_FIELDS.map(({ key, labelKey, placeholder, type }) => (
                <div key={key} className="space-y-1.5">
                  <Label htmlFor={`reg-${key}`}>{t(labelKey)}</Label>
                  <div className="flex gap-2">
                    <Input
                      id={`reg-${key}`}
                      type={type}
                      value={contactValues[key]}
                      onChange={e => setContact(key, e.target.value)}
                      placeholder={placeholder}
                      className="flex-1"
                    />
                    <button
                      type="button"
                      title={t('auth.markPreferred')}
                      aria-label={t('a11y.markPreferred', { method: t(labelKey) })}
                      aria-pressed={preferred === key}
                      disabled={!contactValues[key].trim()}
                      onClick={() => setPreferred(prev => prev === key ? '' : key)}
                      className={`px-2 rounded-md border transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
                        preferred === key
                          ? 'bg-amber-400 border-amber-500 text-white'
                          : 'border-border text-muted-foreground hover:border-amber-400 hover:text-amber-500'
                      }`}
                    >
                      <Star className="w-4 h-4" fill={preferred === key ? 'currentColor' : 'none'} />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {error && <div role="alert" className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">{error}</div>}
            <Button type="submit" className="w-full" disabled={submitting}>{t('auth.createAccountBtn')}</Button>
          </form>
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            {t('auth.hasAccount')}{' '}
            <Link to="/login" className="text-primary underline underline-offset-4">{t('auth.signIn')}</Link>
          </p>
        </CardFooter>
      </Card>
    </main>
  );
}
