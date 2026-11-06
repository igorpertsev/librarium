import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { adminApi, type ReportPeriod } from '../../api/endpoints';
import type { DemandDto } from '../../api/types';
import { useTagName } from '../utils/catalogLists';
import { Badge } from './ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';

type Wanted = DemandDto['waiting'][number];

function WantedTable({ id, title, empty, rows, readersLabel }: {
  id: string;
  title: string;
  empty: string;
  rows: Wanted[];
  readersLabel: string;
}) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby={id} className="space-y-2 min-w-0">
      <h3 id={id} className="font-medium">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('admin.title')}</TableHead>
              <TableHead className="text-right">{readersLabel}</TableHead>
              <TableHead className="text-right">{t('demand.copies')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={`${row.title}-${row.author}`}>
                <TableCell>
                  {row.title}
                  <span className="block text-xs text-muted-foreground">{row.author}</span>
                </TableCell>
                <TableCell className="text-right tabular-nums">{row.readers}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {row.copies}
                  {row.readers > row.copies && (
                    <Badge variant="outline" className="ml-2">{t('demand.buyMore')}</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}

/** Reports: what readers wait for and save, and which tags are borrowed most. */
export function DemandReport({ period }: { period: ReportPeriod }) {
  const { t } = useTranslation();
  const tagName = useTagName();
  const [demand, setDemand] = useState<DemandDto | null>(null);

  useEffect(() => {
    if (!period.date_from || !period.date_to) return;
    let current = true;
    adminApi
      .reportDemand(period)
      .then((data) => current && setDemand(data))
      .catch(() => current && setDemand(null));
    return () => {
      current = false;
    };
  }, [period]);

  if (!demand) return null;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <WantedTable
          id="demand-waiting"
          title={t('demand.waitingTitle')}
          empty={t('demand.nobodyWaiting')}
          rows={demand.waiting}
          readersLabel={t('demand.waitingReaders')}
        />
        <WantedTable
          id="demand-saved"
          title={t('demand.savedTitle')}
          empty={t('demand.nothingSaved')}
          rows={demand.saved}
          readersLabel={t('demand.savedReaders')}
        />
      </div>
      <section aria-labelledby="demand-tags" className="space-y-2">
        <h3 id="demand-tags" className="font-medium">{t('demand.tagsTitle')}</h3>
        {demand.tags.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('reports.noLoans')}</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {demand.tags.map((tag) => (
              <li key={tag.slug} className="rounded-full border border-border px-3 py-1 text-sm">
                {tagName(tag)} <span className="text-muted-foreground tabular-nums">· {tag.loans}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
