import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';
import { adminApi, type ReportPeriod } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { CategoryLoansDto, MonthStatsDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { useFormat } from '../utils/format';
import { getCategoryTranslation } from '../utils/translations';
import { Button } from './ui/button';
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from './ui/chart';

const RANGES = [6, 12, 24];

/** Admin reports: loans, returns and readers per month (with a CSV), and loans by category for
 * the chosen period. Each chart has a table of the same figures for screen readers. */
export function LibraryStatistics({ period }: { period: ReportPeriod }) {
  const { t } = useTranslation();
  const fmt = useFormat();
  const [months, setMonths] = useState(12);
  const [stats, setStats] = useState<MonthStatsDto[] | null>(null);
  const [categories, setCategories] = useState<CategoryLoansDto[] | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let current = true;
    adminApi.reportMonthly(months).then((found) => current && setStats(found), () => current && setStats([]));
    return () => {
      current = false;
    };
  }, [months]);

  useEffect(() => {
    let current = true;
    if (period.date_from && period.date_to) {
      adminApi.reportCategories(period).then((found) => current && setCategories(found), () => current && setCategories([]));
    }
    return () => {
      current = false;
    };
  }, [period]);

  const monthName = useMemo(() => {
    const format = new Intl.DateTimeFormat(fmt.locale, { month: 'short', year: '2-digit', timeZone: 'UTC' });
    return (key: string) => format.format(new Date(`${key}-01T00:00:00Z`));
  }, [fmt.locale]);

  const rows = (stats ?? []).map((m) => ({ ...m, label: monthName(m.month) }));
  const lending: ChartConfig = {
    loans: { label: t('stats.loans'), color: 'var(--chart-1)' },
    returns: { label: t('stats.returns'), color: 'var(--chart-2)' },
  };
  const readers: ChartConfig = {
    active_readers: { label: t('stats.activeReaders'), color: 'var(--chart-1)' },
    new_readers: { label: t('stats.newReaders'), color: 'var(--chart-3)' },
  };

  const download = async () => {
    setDownloading(true);
    const result = await runAction(() => adminApi.monthlyCsv(months));
    setDownloading(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    const url = URL.createObjectURL(result.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `library-by-month-${months}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const maxCategory = Math.max(1, ...(categories ?? []).map((c) => c.loans));

  return (
    <section aria-labelledby="stats-title" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="stats-title" className="text-lg">{t('stats.title')}</h3>
        <div className="flex items-center gap-2">
          <div role="group" aria-label={t('stats.range')} className="flex gap-1">
            {RANGES.map((value) => (
              <Button key={value} size="sm" variant={months === value ? 'default' : 'outline'} aria-pressed={months === value} onClick={() => setMonths(value)}>
                {t('stats.months', { count: value })}
              </Button>
            ))}
          </div>
          <Button size="sm" variant="outline" onClick={download} disabled={downloading}>
            <Download className="w-4 h-4 mr-1" aria-hidden="true" />
            CSV
          </Button>
        </div>
      </div>

      {stats === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <figure className="space-y-2">
            <figcaption className="text-sm font-medium">{t('stats.lendingChart')}</figcaption>
            <div aria-hidden="true">
              <ChartContainer config={lending} className="h-56 w-full aspect-auto">
                <BarChart data={rows}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} width={32} tickLine={false} axisLine={false} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <ChartLegend content={<ChartLegendContent />} />
                  <Bar dataKey="loans" fill="var(--color-loans)" radius={3} />
                  <Bar dataKey="returns" fill="var(--color-returns)" radius={3} />
                </BarChart>
              </ChartContainer>
            </div>
          </figure>
          <figure className="space-y-2">
            <figcaption className="text-sm font-medium">{t('stats.readersChart')}</figcaption>
            <div aria-hidden="true">
              <ChartContainer config={readers} className="h-56 w-full aspect-auto">
                <LineChart data={rows}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} width={32} tickLine={false} axisLine={false} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <ChartLegend content={<ChartLegendContent />} />
                  <Line dataKey="active_readers" stroke="var(--color-active_readers)" strokeWidth={2} dot={false} />
                  <Line dataKey="new_readers" stroke="var(--color-new_readers)" strokeWidth={2} dot={false} />
                </LineChart>
              </ChartContainer>
            </div>
          </figure>
          <details className="lg:col-span-2 text-sm">
            <summary className="cursor-pointer">{t('stats.showTable')}</summary>
            <table className="mt-2 w-full">
              <caption className="sr-only">{t('stats.title')}</caption>
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th scope="col" className="font-normal py-1">{t('stats.month')}</th>
                  <th scope="col" className="font-normal py-1">{t('stats.loans')}</th>
                  <th scope="col" className="font-normal py-1">{t('stats.returns')}</th>
                  <th scope="col" className="font-normal py-1">{t('stats.activeReaders')}</th>
                  <th scope="col" className="font-normal py-1">{t('stats.newReaders')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.month} className="border-t border-border tabular-nums">
                    <th scope="row" className="font-normal py-1 text-left">{row.label}</th>
                    <td>{row.loans}</td>
                    <td>{row.returns}</td>
                    <td>{row.active_readers}</td>
                    <td>{row.new_readers}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </div>
      )}

      <div className="space-y-2">
        <h4 className="text-sm font-medium">{t('stats.byCategory')}</h4>
        {categories === null ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : categories.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('stats.noLoans')}</p>
        ) : (
          <ul className="space-y-1">
            {categories.map((row) => (
              <li key={row.category} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-2 text-sm">
                <span className="truncate">{getCategoryTranslation(t, row.category)}</span>
                <span className="h-2 rounded bg-muted overflow-hidden" aria-hidden="true">
                  <span className="block h-full bg-primary" style={{ width: `${(row.loans / maxCategory) * 100}%` }} />
                </span>
                <span className="tabular-nums text-right">{row.loans}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
