import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2, Users } from 'lucide-react';
import { toast } from 'sonner';
import { useFamily } from '../contexts/FamilyContext';
import { errorMessage } from '../utils/apiErrors';
import { useConfirm } from './ConfirmDialog';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';

/** Profile: children in the family account (own reading logs; orders can be for them). */
export function FamilyCard() {
  const { t } = useTranslation();
  const { children, addChild, removeChild } = useFamily();
  const { confirm, confirmDialog } = useConfirm();
  const [name, setName] = useState('');
  const [year, setYear] = useState('');
  const [busy, setBusy] = useState(false);

  const add = async () => {
    setBusy(true);
    const result = await addChild(name.trim(), year ? Number.parseInt(year, 10) : null);
    setBusy(false);
    if (result.ok) {
      toast.success(t('family.added', { name: name.trim() }));
      setName('');
      setYear('');
    } else {
      toast.error(errorMessage(t, result.error));
    }
  };

  const remove = async (id: string, childName: string) => {
    const ok = await confirm({
      title: t('family.removeTitle', { name: childName }),
      description: t('family.removeDesc'),
      confirmLabel: t('confirm.remove'),
      destructive: true,
    });
    if (!ok) return;
    const result = await removeChild(id);
    if (!result.ok) toast.error(errorMessage(t, result.error));
  };

  return (
    <Card data-testid="family">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="w-5 h-5" aria-hidden="true" />
          {t('family.title')}
        </CardTitle>
        <CardDescription>{t('family.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {children.length > 0 && (
          <ul className="space-y-2">
            {children.map((child) => (
              <li key={child.id} className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
                <span>
                  {child.name}
                  {child.birth_year && <span className="text-sm text-muted-foreground"> · {child.birth_year}</span>}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('family.remove', { name: child.name })}
                  onClick={() => void remove(child.id, child.name)}
                >
                  <Trash2 className="w-4 h-4" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void add();
          }}
        >
          <div className="space-y-1 flex-1 min-w-[10rem]">
            <Label htmlFor="child-name">{t('family.name')}</Label>
            <Input id="child-name" maxLength={100} required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1 w-28">
            <Label htmlFor="child-year">{t('family.birthYear')}</Label>
            <Input
              id="child-year"
              type="number"
              min={1990}
              max={new Date().getFullYear()}
              value={year}
              onChange={(e) => setYear(e.target.value)}
            />
          </div>
          <Button type="submit" variant="outline" disabled={busy || !name.trim()}>
            {t('family.add')}
          </Button>
        </form>
      </CardContent>
      {confirmDialog}
    </Card>
  );
}
