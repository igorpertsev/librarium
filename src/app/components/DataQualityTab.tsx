import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pencil } from 'lucide-react';
import { adminApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import type { QualityIssueDto, QualitySummaryDto } from '../../api/types';
import { useCatalog } from '../contexts/CatalogContext';
import type { Book } from '../types';
import { Button } from './ui/button';

const ISSUES: QualityIssueDto[] = [
  'machine_translation',
  'no_cover',
  'no_description',
  'no_tags',
  'no_translation',
  'no_isbn',
];
const PAGE_SIZE = 20;

/** Admin: titles with gaps in their catalogue data, to fix one by one. */
export function DataQualityTab({ onEdit }: { onEdit: (book: Book) => void }) {
  const { t } = useTranslation();
  const { version } = useCatalog();
  const [summary, setSummary] = useState<QualitySummaryDto | null>(null);
  const [issue, setIssue] = useState<QualityIssueDto>('machine_translation');
  const [books, setBooks] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  useEffect(() => {
    adminApi.bookQuality().then(setSummary).catch(() => setSummary(null));
  }, [version]);

  useEffect(() => {
    let current = true;
    adminApi
      .listBooks({ quality: issue, page, page_size: PAGE_SIZE, sort: 'title' })
      .then((result) => {
        if (!current) return;
        setBooks(result.items.map(bookFromDto));
        setTotal(result.total);
      })
      .catch(() => current && setBooks([]));
    return () => {
      current = false;
    };
  }, [issue, page, version]);

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg">{t('quality.title')}</h2>
        <p className="text-sm text-muted-foreground">
          {summary ? t('quality.description', { count: summary.titles }) : t('common.loading')}
        </p>
      </div>
      <div role="group" aria-label={t('quality.title')} className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {ISSUES.map((key) => {
          const count = summary?.issues[key] ?? 0;
          const selected = key === issue;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={selected}
              onClick={() => {
                setIssue(key);
                setPage(1);
              }}
              className={`rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                selected ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted'
              }`}
            >
              <span className="block text-2xl tabular-nums">{summary ? count : '—'}</span>
              <span className="block text-sm text-muted-foreground">{t(`quality.issue.${key}`)}</span>
            </button>
          );
        })}
      </div>

      <div className="space-y-2" aria-live="polite">
        {books.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">{t('quality.none')}</p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {books.map((book) => (
              <li key={book.id} className="flex items-center gap-3 p-3">
                <div className="w-8 h-11 shrink-0 overflow-hidden rounded bg-muted">
                  {book.coverImage && <img src={book.coverImage} alt="" className="w-full h-full object-cover" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="truncate">{book.title}</p>
                  <p className="text-sm text-muted-foreground truncate">{book.author}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => onEdit(book)}>
                  <Pencil className="w-4 h-4 mr-1" aria-hidden="true" />
                  {t('quality.fix')}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {pages > 1 && (
          <div className="flex items-center justify-end gap-2 text-sm">
            <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              {t('quality.previous')}
            </Button>
            <span className="tabular-nums">{page} / {pages}</span>
            <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              {t('quality.next')}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
