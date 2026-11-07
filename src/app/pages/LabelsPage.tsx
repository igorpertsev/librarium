import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';
import { Printer } from 'lucide-react';
import { adminApi } from '../../api/endpoints';
import { Button } from '../components/ui/button';
import { copyIdFrom, labelUrl } from '../utils/labels';

interface Label {
  id: string;
  title: string;
  author: string;
  qr: string;
}

const MAX_LABELS = 120;

/** Printable labels for the selected copies: a QR code of the book page, the title, the author
 * and the start of the copy id. ``/admin/labels?ids=<id>,<id>``. */
export default function LabelsPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const ids = (params.get('ids') ?? '')
    .split(',')
    .map((value) => copyIdFrom(value))
    .filter((value): value is string => value !== null)
    .slice(0, MAX_LABELS);
  const key = ids.join(',');
  const [labels, setLabels] = useState<Label[] | null>(null);

  useEffect(() => {
    document.title = `${t('labels.title')} — Little Dragon`;
  }, [t]);

  useEffect(() => {
    let current = true;
    const wanted = key ? key.split(',') : [];
    (async () => {
      const QRCode = await import('qrcode');
      const found = await Promise.all(
        wanted.map(async (copyId) => {
          const book = await adminApi.getBook(copyId).catch(() => null);
          if (!book) return null;
          const qr = await QRCode.toDataURL(labelUrl(copyId), { margin: 1, width: 240, errorCorrectionLevel: 'M' });
          return { id: copyId, title: book.title, author: book.author, qr };
        }),
      );
      if (current) setLabels(found.filter((label): label is Label => label !== null));
    })().catch(() => current && setLabels([]));
    return () => {
      current = false;
    };
  }, [key]);

  return (
    <div className="container mx-auto px-4 py-6 space-y-4 print:p-0 print:max-w-none">
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <div>
          <h1 className="text-2xl">{t('labels.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('labels.hint')}</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="ghost">
            <Link to="/admin">{t('labels.back')}</Link>
          </Button>
          <Button onClick={() => window.print()} disabled={!labels || labels.length === 0}>
            <Printer className="w-4 h-4 mr-1" aria-hidden="true" />
            {t('labels.print')}
          </Button>
        </div>
      </div>
      {labels === null ? (
        <p className="text-muted-foreground">{t('common.loading')}</p>
      ) : labels.length === 0 ? (
        <p className="text-muted-foreground">{t('labels.none')}</p>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3 print:grid-cols-3 print:gap-0" aria-label={t('labels.title')}>
          {labels.map((label) => (
            <li
              key={label.id}
              className="flex items-center gap-3 rounded-md border border-border bg-white p-3 text-black break-inside-avoid print:rounded-none print:border-dashed"
            >
              <img src={label.qr} alt={t('labels.qrAlt', { title: label.title })} className="w-24 h-24 shrink-0" />
              <div className="min-w-0 text-sm">
                <p className="font-medium line-clamp-3">{label.title}</p>
                <p className="text-xs line-clamp-1">{label.author}</p>
                <p className="mt-1 font-mono text-[10px]">{label.id.slice(0, 8)}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
