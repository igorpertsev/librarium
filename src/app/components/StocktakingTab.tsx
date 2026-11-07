import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Minus, Plus, ScanBarcode } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { ScanResultDto, StocktakeBriefDto, StocktakeReportDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { useConfirm } from './ConfirmDialog';
import { IsbnScanner } from './IsbnScanner';
import { Button } from './ui/button';
import { Checkbox } from './ui/checkbox';
import { Label } from './ui/label';
import { cn } from './ui/utils';

type Filter = 'differences' | 'all';

/** Admin: count the books on the shelves and compare with the catalogue. */
export function StocktakingTab() {
  const { t } = useTranslation();
  const fmt = useFormat();
  const { confirm, confirmDialog } = useConfirm();
  const [history, setHistory] = useState<StocktakeBriefDto[] | null>(null);
  const [report, setReport] = useState<StocktakeReportDto | null>(null);
  const [scanning, setScanning] = useState(false);
  const [recent, setRecent] = useState<ScanResultDto[]>([]);
  const [filter, setFilter] = useState<Filter>('differences');
  const [markMissing, setMarkMissing] = useState(true);
  const [busy, setBusy] = useState(false);

  const open = history?.find((take) => take.finished_at === null) ?? null;

  const loadReport = useCallback(async (takeId: string) => {
    setReport(await adminApi.stocktakeReport(takeId));
  }, []);

  const load = useCallback(async () => {
    const takes = await adminApi.stocktakes().catch(() => []);
    setHistory(takes);
    const current = takes.find((take) => take.finished_at === null);
    if (current) await loadReport(current.id).catch(() => undefined);
    else setReport(null);
  }, [loadReport]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async <T,>(action: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    const result = await runAction(action);
    setBusy(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return null;
    }
    return result.data;
  };

  const start = async () => {
    if (await act(() => adminApi.startStocktake())) await load();
  };

  const scan = async (isbn: string) => {
    if (!open) return;
    const result = await act(() => adminApi.stocktakeScan(open.id, isbn));
    if (!result) return;
    setRecent((items) => [result, ...items].slice(0, 5));
    if (!result.found) toast.warning(t('stock.unknown', { isbn: result.isbn }));
    await loadReport(open.id);
  };

  const count = async (bookId: string, delta: 1 | -1) => {
    if (!open) return;
    if (await act(() => adminApi.stocktakeCount(open.id, bookId, delta))) await loadReport(open.id);
  };

  const finish = async () => {
    if (!open || !report) return;
    const missing = report.lines.reduce((sum, line) => sum + Math.max(line.expected - line.counted, 0), 0);
    const ok = await confirm({
      title: t('stock.finishTitle'),
      description: markMissing && missing > 0 ? t('stock.finishMark', { count: missing }) : t('stock.finishKeep'),
      confirmLabel: t('stock.finish'),
    });
    if (!ok) return;
    const done = await act(() => adminApi.finishStocktake(open.id, markMissing));
    if (done) {
      toast.success(t('stock.finished', { count: done.marked_missing }));
      setRecent([]);
      await load();
      setReport(done);
    }
  };

  const lines = useMemo(
    () => (report?.lines ?? []).filter((line) => filter === 'all' || line.counted !== line.expected),
    [report, filter],
  );
  const missing = (report?.lines ?? []).reduce((sum, l) => sum + Math.max(l.expected - l.counted, 0), 0);
  const extra = (report?.lines ?? []).reduce((sum, l) => sum + Math.max(l.counted - l.expected, 0), 0);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg">{t('stock.title')}</h2>
        <p className="text-sm text-muted-foreground">{t('stock.description')}</p>
      </div>

      {!open && (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={start} disabled={busy || history === null}>
            {t('stock.start')}
          </Button>
          {history && history.length > 0 && (
            <p className="text-sm text-muted-foreground">
              {t('stock.last', {
                date: fmt.dateTime(history[0].finished_at ?? history[0].started_at),
                count: history[0].marked_missing,
              })}
            </p>
          )}
        </div>
      )}

      {report && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            {open && (
              <Button onClick={() => setScanning(true)}>
                <ScanBarcode className="w-4 h-4 mr-2" aria-hidden="true" />
                {t('stock.scan')}
              </Button>
            )}
            <p className="text-sm" role="status">
              {t('stock.progress', { counted: report.counted, expected: report.expected })}
              {' · '}
              {t('stock.missing', { count: missing })}
              {' · '}
              {t('stock.extra', { count: extra })}
            </p>
          </div>

          {recent.length > 0 && (
            <ul className="text-sm space-y-0.5" aria-label={t('stock.recent')}>
              {recent.map((item, i) => (
                <li key={`${item.isbn}-${i}`} className={item.found ? undefined : 'text-destructive dark:text-red-400'}>
                  {item.found
                    ? t('stock.counted', { title: item.title, counted: item.counted, expected: item.expected })
                    : t('stock.unknown', { isbn: item.isbn })}
                </li>
              ))}
            </ul>
          )}

          <div role="group" aria-label={t('stock.show')} className="flex gap-2">
            {(['differences', 'all'] as const).map((key) => (
              <Button
                key={key}
                size="sm"
                variant={filter === key ? 'default' : 'outline'}
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                {t(`stock.filter.${key}`)}
              </Button>
            ))}
          </div>

          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">{t('stock.noDifferences')}</p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left">
                  <tr>
                    <th className="px-3 py-2 font-medium">{t('admin.title')}</th>
                    <th className="px-3 py-2 font-medium">ISBN</th>
                    <th className="px-3 py-2 font-medium text-right">{t('stock.expected')}</th>
                    <th className="px-3 py-2 font-medium text-right">{t('stock.countedHead')}</th>
                    <th className="px-3 py-2 font-medium text-right">{t('stock.onLoan')}</th>
                    {open && <th className="px-3 py-2"><span className="sr-only">{t('stock.byHand')}</span></th>}
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => {
                    const diff = line.counted - line.expected;
                    return (
                      <tr key={line.book_id} className="border-t border-border">
                        <td className="px-3 py-2">
                          <span className="font-medium">{line.title}</span>
                          <span className="block text-xs text-muted-foreground">{line.author}</span>
                        </td>
                        <td className="px-3 py-2 text-xs tabular-nums">{line.isbn ?? '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{line.expected}</td>
                        <td
                          className={cn(
                            'px-3 py-2 text-right tabular-nums font-medium',
                            diff < 0 && 'text-destructive dark:text-red-400',
                            diff > 0 && 'text-amber-700 dark:text-amber-400',
                          )}
                        >
                          {line.counted}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{line.on_loan}</td>
                        {open && (
                          <td className="px-3 py-2">
                            <div className="flex justify-end gap-1">
                              <Button
                                size="icon"
                                variant="ghost"
                                aria-label={t('stock.less', { title: line.title })}
                                disabled={busy || line.counted === 0}
                                onClick={() => count(line.book_id, -1)}
                              >
                                <Minus className="w-4 h-4" aria-hidden="true" />
                              </Button>
                              <Button
                                size="icon"
                                variant="outline"
                                aria-label={t('stock.more', { title: line.title })}
                                disabled={busy}
                                onClick={() => count(line.book_id, 1)}
                              >
                                <Plus className="w-4 h-4" aria-hidden="true" />
                              </Button>
                            </div>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {report.unknown_isbns.length > 0 && (
            <div className="text-sm">
              <p className="font-medium">{t('stock.unknownTitle')}</p>
              <p className="text-muted-foreground">
                {report.unknown_isbns.map((item) => `${item.isbn} ×${item.counted}`).join(', ')}
              </p>
            </div>
          )}

          {open && (
            <div className="flex flex-wrap items-center gap-4 border-t border-border pt-4">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="mark-missing"
                  checked={markMissing}
                  onCheckedChange={(checked) => setMarkMissing(checked === true)}
                />
                <Label htmlFor="mark-missing">{t('stock.markMissing')}</Label>
              </div>
              <Button variant="outline" onClick={finish} disabled={busy}>
                {t('stock.finish')}
              </Button>
            </div>
          )}
        </>
      )}

      <IsbnScanner open={scanning} continuous onClose={() => setScanning(false)} onDetected={(isbn) => void scan(isbn)} />
      {confirmDialog}
    </div>
  );
}
