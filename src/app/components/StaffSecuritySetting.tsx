import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { errorMessage } from '../utils/apiErrors';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

/** Admin: require two-step sign-in for librarians and administrators. */
export function StaffSecuritySetting() {
  const { t } = useTranslation();
  const [required, setRequired] = useState<boolean | null>(null);

  useEffect(() => {
    adminApi.getSettings().then((s) => setRequired(s.require_staff_mfa), () => undefined);
  }, []);

  const change = async (next: boolean) => {
    const result = await runAction(() => adminApi.updateSettings({ require_staff_mfa: next }));
    if (result.ok) {
      setRequired(result.data.require_staff_mfa);
      toast.success(next ? t('mfa.requiredOn') : t('mfa.requiredOff'));
    } else {
      toast.error(errorMessage(t, result.error));
    }
  };

  return (
    <div className="space-y-2 border-t border-border pt-4">
      <div className="flex items-center gap-2">
        <Switch id="requireStaffMfa" checked={required ?? false} disabled={required === null} onCheckedChange={(v) => void change(v)} />
        <Label htmlFor="requireStaffMfa">{t('mfa.requireStaff')}</Label>
      </div>
      <p className="text-xs text-muted-foreground">{t('mfa.requireStaffHint')}</p>
    </div>
  );
}
