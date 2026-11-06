import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { errorMessage } from '../utils/apiErrors';
import { invalidateLibraryRules } from '../utils/useLibraryRules';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';

/** Admin: loan period and how often customers may extend a loan. */
export function LoanRulesSettings() {
  const { t } = useTranslation();
  const [loanPeriodDays, setLoanPeriodDays] = useState('');
  const [maxRenewals, setMaxRenewals] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    adminApi.getSettings().then(
      (settings) => {
        setLoanPeriodDays(String(settings.loan_period_days));
        setMaxRenewals(String(settings.max_renewals));
      },
      () => undefined,
    );
  }, []);

  const handleSave = async () => {
    setSaving(true);
    const result = await runAction(() =>
      adminApi.updateSettings({
        loan_period_days: Number.parseInt(loanPeriodDays, 10),
        max_renewals: Number.parseInt(maxRenewals, 10),
      }),
    );
    setSaving(false);
    if (result.ok) {
      invalidateLibraryRules();
      toast.success(t('admin.loanRulesUpdated'));
    } else {
      toast.error(errorMessage(t, result.error));
    }
  };

  return (
    <div className="space-y-4 border-t border-border pt-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="loanPeriodDays">{t('admin.loanPeriodDays')}</Label>
          <Input
            id="loanPeriodDays"
            type="number"
            min="1"
            max="365"
            value={loanPeriodDays}
            onChange={(e) => setLoanPeriodDays(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="maxRenewals">{t('admin.maxRenewals')}</Label>
          <Input
            id="maxRenewals"
            type="number"
            min="0"
            max="10"
            value={maxRenewals}
            onChange={(e) => setMaxRenewals(e.target.value)}
          />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{t('admin.loanRulesHint')}</p>
      <Button variant="outline" onClick={handleSave} disabled={saving || !loanPeriodDays || !maxRenewals}>
        {t('admin.saveLoanRules')}
      </Button>
    </div>
  );
}
