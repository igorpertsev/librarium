import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileUp } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { BookImportResultDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';

const TEMPLATE =
  'title,author,category,age_range,isbn,publication_year,language,status,cover_url,description\n' +
  'The Hobbit,J.R.R. Tolkien,fiction,8+,9780547928227,1937,en,available,,"A hobbit, a dragon and a long journey."\n';
const MAX_SHOWN_ERRORS = 20;

/** Admin: create many books at once from a CSV file (validated first, all or nothing). */
export function BookImportDialog({ onImported }: { onImported: () => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [csv, setCsv] = useState<string | null>(null);
  const [fileName, setFileName] = useState('');
  const [preview, setPreview] = useState<BookImportResultDto | null>(null);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setCsv(null);
    setFileName('');
    setPreview(null);
  };

  const handleFile = async (file: File | undefined) => {
    reset();
    if (!file) return;
    const text = await file.text();
    setFileName(file.name);
    setCsv(text);
    setBusy(true);
    const result = await runAction(() => adminApi.importBooks(text, true));
    setBusy(false);
    if (result.ok) setPreview(result.data);
    else toast.error(errorMessage(t, result.error));
  };

  const handleImport = async () => {
    if (!csv) return;
    setBusy(true);
    const result = await runAction(() => adminApi.importBooks(csv, false));
    setBusy(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
    } else if (result.data.errors.length > 0) {
      setPreview(result.data);
    } else {
      toast.success(t('bookImport.done', { count: result.data.created }));
      setOpen(false);
      reset();
      onImported();
    }
  };

  const templateHref = `data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`;
  const ready = preview !== null && preview.errors.length === 0 && preview.rows > 0;

  return (
    <>
      <Button variant="outline" onClick={() => { reset(); setOpen(true); }}>
        <FileUp className="w-4 h-4 mr-2" aria-hidden="true" />
        {t('bookImport.button')}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t('bookImport.title')}</DialogTitle>
            <DialogDescription>{t('bookImport.description')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <a href={templateHref} download="books-template.csv" className="text-sm text-primary underline underline-offset-4">
              {t('bookImport.template')}
            </a>
            <div className="space-y-2">
              <Label htmlFor="book-import-file">{t('bookImport.file')}</Label>
              <Input
                id="book-import-file"
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => handleFile(e.target.files?.[0])}
              />
            </div>
            {busy && <p role="status" className="text-sm text-muted-foreground">{t('common.loading')}</p>}
            {preview && !busy && (
              <div role="status" className="space-y-2 text-sm">
                {ready ? (
                  <p>{t('bookImport.ready', { count: preview.rows, file: fileName })}</p>
                ) : preview.rows === 0 && preview.errors.length === 0 ? (
                  <p>{t('bookImport.empty')}</p>
                ) : (
                  <>
                    <p className="text-destructive">{t('bookImport.invalid', { count: preview.errors.length })}</p>
                    <ul className="max-h-48 overflow-y-auto rounded-md border border-border p-2 space-y-1 font-mono text-xs">
                      {preview.errors.slice(0, MAX_SHOWN_ERRORS).map((error, index) => (
                        <li key={index}>{t('bookImport.line', { row: error.row })}: {error.message}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{t('admin.cancel')}</Button>
            <Button onClick={handleImport} disabled={!ready || busy}>
              {ready ? t('bookImport.import', { count: preview.rows }) : t('bookImport.importNone')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
