import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi, type ReportPeriod } from '../../api/endpoints';
import { runAction, type ApiError } from '../../api/errors';
import type { ReportSummaryDto } from '../../api/types';
import { toMoney } from '../../api/mappers';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';

const isoDay = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

function lastDays(days: number): ReportPeriod {
  const end = new Date();
  const start = new Date(end.getFullYear(), end.getMonth(), end.getDate() - (days - 1));
  return { date_from: isoDay(start), date_to: isoDay(end) };
}

/** Admin: lending summary for a period, most borrowed books and a CSV export of orders. */
export function ReportsTab() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const [period, setPeriod] = useState<ReportPeriod>(() => lastDays(30));
  const [report, setReport] = useState<ReportSummaryDto | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async (value: ReportPeriod) => {
    const result = await runAction(() => adminApi.reportSummary(value));
    if (result.ok) {
      setReport(result.data);
      setError(null);
    } else {
      setError(result.error);
    }
  }, []);

  useEffect(() => {
    if (period.date_from && period.date_to) load(period);
  }, [period, load]);

  const download = async () => {
    setDownloading(true);
    const result = await runAction(() => adminApi.ordersCsv(period));
    setDownloading(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    const url = URL.createObjectURL(result.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `orders-${period.date_from}-to-${period.date_to}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const tiles: Array<[string, string]> = report
    ? [
        [t('reports.ordersPlaced'), String(report.orders_placed)],
        [t('reports.loans'), String(report.orders_confirmed)],
        [t('reports.booksLent'), String(report.books_lent)],
        [t('reports.booksReturned'), String(report.books_returned)],
        [t('reports.readers'), String(report.active_readers)],
        [t('reports.revenue'), fmt.money(toMoney(report.revenue), report.currency ?? 'USD')],
        [t('reports.overdueNow'), String(report.overdue_now)],
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-2">
          <Label htmlFor="report-from">{t('reports.from')}</Label>
          <Input id="report-from" type="date" value={period.date_from} max={period.date_to}
            onChange={(e) => setPeriod({ ...period, date_from: e.target.value })} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="report-to">{t('reports.to')}</Label>
          <Input id="report-to" type="date" value={period.date_to} min={period.date_from}
            onChange={(e) => setPeriod({ ...period, date_to: e.target.value })} />
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setPeriod(lastDays(7))}>{t('reports.last7')}</Button>
          <Button variant="outline" size="sm" onClick={() => setPeriod(lastDays(30))}>{t('reports.last30')}</Button>
          <Button variant="outline" size="sm" onClick={() => setPeriod(lastDays(365))}>{t('reports.last365')}</Button>
        </div>
        <Button onClick={download} disabled={downloading} className="ml-auto">
          <Download className="w-4 h-4 mr-2" aria-hidden="true" />
          {t('reports.downloadCsv')}
        </Button>
      </div>

      {error && <p role="alert" className="text-sm text-destructive">{errorMessage(t, error)}</p>}

      {report && (
        <>
          <dl className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            {tiles.map(([label, value]) => (
              <div key={label} className="rounded-lg border border-border p-3">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="text-2xl mt-1">{value}</dd>
              </div>
            ))}
          </dl>

          <section aria-labelledby="top-books-title" className="space-y-2">
            <h3 id="top-books-title" className="font-medium">{t('reports.topBooks')}</h3>
            {report.top_books.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('reports.noLoans')}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">#</TableHead>
                    <TableHead>{t('admin.title')}</TableHead>
                    <TableHead>{t('admin.author')}</TableHead>
                    <TableHead className="text-right">{t('reports.timesLent')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.top_books.map((book, index) => (
                    <TableRow key={`${book.title}-${book.author}`}>
                      <TableCell className="text-muted-foreground">{index + 1}</TableCell>
                      <TableCell>{book.title}</TableCell>
                      <TableCell>{book.author}</TableCell>
                      <TableCell className="text-right">{book.loans}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
