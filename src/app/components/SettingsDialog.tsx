import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import type { UiLanguage } from '../types';
import { setThemePreference, useTheme, type ThemePreference } from '../utils/theme';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Download } from 'lucide-react';
import { Button } from './ui/button';
import { useInstallPrompt } from '../utils/pwa';

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const { t, i18n } = useTranslation();
  const { setLanguage } = useAuth();
  const { preference: theme } = useTheme();
  const { canInstall, install } = useInstallPrompt();

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
          <div className="space-y-2">
            <Label htmlFor="theme">{t('settings.theme')}</Label>
            <Select value={theme} onValueChange={(value) => setThemePreference(value as ThemePreference)}>
              <SelectTrigger id="theme">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system">{t('settings.themeSystem')}</SelectItem>
                <SelectItem value="light">{t('settings.themeLight')}</SelectItem>
                <SelectItem value="dark">{t('settings.themeDark')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {canInstall && (
            <div className="space-y-2 border-t border-border pt-4">
              <p className="text-sm text-muted-foreground">{t('pwa.installHint')}</p>
              <Button variant="outline" onClick={() => void install()}>
                <Download className="w-4 h-4 mr-2" aria-hidden="true" />
                {t('pwa.install')}
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
