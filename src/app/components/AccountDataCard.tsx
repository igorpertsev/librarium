import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Download, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { usersApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import { useAuth } from '../contexts/AuthContext';
import { errorMessage } from '../utils/apiErrors';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';

/** Profile: download everything stored about me, or delete my account. */
export function AccountDataCard() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState('');

  const download = async () => {
    setDownloading(true);
    const result = await runAction(() => usersApi.exportData());
    setDownloading(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    const url = URL.createObjectURL(result.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'little-dragon-my-data.json';
    link.click();
    URL.revokeObjectURL(url);
  };

  const remove = async (e: FormEvent) => {
    e.preventDefault();
    setDeleting(true);
    const result = await runAction(() => usersApi.deleteMe(password));
    setDeleting(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    setOpen(false);
    toast.success(t('accountData.deleted'));
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('accountData.title')}</CardTitle>
        <CardDescription>{t('accountData.description')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={download} disabled={downloading}>
          <Download className="w-4 h-4 mr-2" aria-hidden="true" />
          {t('accountData.download')}
        </Button>
        {user?.role !== 'admin' && (
          <Button variant="outline" className="text-destructive dark:text-red-400" onClick={() => setOpen(true)}>
            <Trash2 className="w-4 h-4 mr-2" aria-hidden="true" />
            {t('accountData.delete')}
          </Button>
        )}
      </CardContent>
      <Dialog open={open} onOpenChange={(value) => { setOpen(value); if (!value) setPassword(''); }}>
        <DialogContent>
          <form onSubmit={remove} className="space-y-4">
            <DialogHeader>
              <DialogTitle>{t('accountData.deleteTitle')}</DialogTitle>
              <DialogDescription>{t('accountData.deleteDescription')}</DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="delete-password">{t('accountData.password')}</Label>
              <Input
                id="delete-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>{t('admin.cancel')}</Button>
              <Button type="submit" variant="destructive" disabled={deleting || !password}>
                {t('accountData.deleteConfirm')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
