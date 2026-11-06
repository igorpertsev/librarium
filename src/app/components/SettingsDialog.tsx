import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import type { UiLanguage } from '../types';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const { t, i18n } = useTranslation();
  const { setLanguage } = useAuth();

  // Also saved on the account when signed in, so emails use the same language.
  const handleLanguageChange = (language: string) => {
    void setLanguage(language as UiLanguage);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('settings.title')}</DialogTitle>
          <DialogDescription>{t('settings.languageDesc')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="language">{t('settings.language')}</Label>
            <Select value={i18n.language} onValueChange={handleLanguageChange}>
              <SelectTrigger id="language">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">{t('settings.english')}</SelectItem>
                <SelectItem value="ru">{t('settings.russian')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
