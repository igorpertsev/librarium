import { FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GitMerge, Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi } from '../../api/endpoints';
import { runAction, type ActionResult } from '../../api/errors';
import type { SeriesDto, TagDto } from '../../api/types';
import { useCatalog } from '../contexts/CatalogContext';
import { errorMessage } from '../utils/apiErrors';
import { useSeriesList, useTagList, useTagName } from '../utils/catalogLists';
import { useConfirm } from './ConfirmDialog';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Textarea } from './ui/textarea';

type Editing =
  | { kind: 'tag'; tag: TagDto }
  | { kind: 'series'; series: SeriesDto }
  | { kind: 'merge-tag'; tag: TagDto }
  | { kind: 'merge-series'; series: SeriesDto }
  | null;

/** Admin: the tag list and the series, with book counts; rename, merge and delete. */
export function TagsSeriesTab({ onChanged }: { onChanged: () => void }) {
  const { t } = useTranslation();
  const tagName = useTagName();
  const { invalidateCatalog } = useCatalog();
  const { items: tags } = useTagList();
  const { items: series } = useSeriesList();
  const { confirm, confirmDialog } = useConfirm();
  const [editing, setEditing] = useState<Editing>(null);
  const [newTag, setNewTag] = useState({ name_en: '', name_ru: '' });
  const [newSeries, setNewSeries] = useState('');
  const [seriesQuery, setSeriesQuery] = useState('');

  /** Toast the outcome; on success reload every list that shows tags or series. */
  const finish = <T,>(result: ActionResult<T>, successKey: string): boolean => {
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return false;
    }
    toast.success(t(successKey));
    invalidateCatalog();
    onChanged();
    return true;
  };

  const addTag = async (e: FormEvent) => {
    e.preventDefault();
    const result = await runAction(() =>
      adminApi.createTag({ name_en: newTag.name_en.trim(), name_ru: newTag.name_ru.trim() }),
    );
    if (finish(result, 'catalogAdmin.tagAdded')) setNewTag({ name_en: '', name_ru: '' });
  };

  const addSeries = async (e: FormEvent) => {
    e.preventDefault();
    const result = await runAction(() => adminApi.createSeries({ name: newSeries.trim(), description: '' }));
    if (finish(result, 'catalogAdmin.seriesAdded')) setNewSeries('');
  };

  const deleteTag = async (tag: TagDto) => {
    const ok = await confirm({
      title: t('catalogAdmin.deleteTagTitle', { name: tagName(tag) }),
      description: t('catalogAdmin.deleteTagDesc', { count: tag.book_count }),
      confirmLabel: t('catalogAdmin.delete'),
      destructive: true,
    });
    if (ok) finish(await runAction(() => adminApi.deleteTag(tag.id)), 'catalogAdmin.tagDeleted');
  };

  const deleteSeries = async (item: SeriesDto) => {
    const ok = await confirm({
      title: t('catalogAdmin.deleteSeriesTitle', { name: item.name }),
      description: t('catalogAdmin.deleteSeriesDesc', { count: item.book_count }),
      confirmLabel: t('catalogAdmin.delete'),
      destructive: true,
    });
    if (ok) finish(await runAction(() => adminApi.deleteSeries(item.id)), 'catalogAdmin.seriesDeleted');
  };

  const sortedTags = [...tags].sort((a, b) => tagName(a).localeCompare(tagName(b)));
  const query = seriesQuery.trim().toLowerCase();
  const shownSeries = query ? series.filter((item) => item.name.toLowerCase().includes(query)) : series;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <section aria-labelledby="tags-heading" className="space-y-4 min-w-0">
        <div>
          <h2 id="tags-heading" className="text-lg">{t('catalogAdmin.tagsTitle')}</h2>
          <p className="text-sm text-muted-foreground">{t('catalogAdmin.tagsDesc')}</p>
        </div>
        <form onSubmit={addTag} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <div className="space-y-1">
            <Label htmlFor="new-tag-en">{t('catalogAdmin.nameEn')}</Label>
            <Input
              id="new-tag-en"
              value={newTag.name_en}
              maxLength={64}
              onChange={(e) => setNewTag({ ...newTag, name_en: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="new-tag-ru">{t('catalogAdmin.nameRu')}</Label>
            <Input
              id="new-tag-ru"
              value={newTag.name_ru}
              maxLength={64}
              onChange={(e) => setNewTag({ ...newTag, name_ru: e.target.value })}
            />
          </div>
          <Button type="submit" disabled={!newTag.name_en.trim() || !newTag.name_ru.trim()}>
            <Plus className="w-4 h-4 mr-1" aria-hidden="true" />
            {t('catalogAdmin.add')}
          </Button>
        </form>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('catalogAdmin.tag')}</TableHead>
                <TableHead className="text-right">{t('catalogAdmin.books')}</TableHead>
                <TableHead>{t('admin.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedTags.map((tag) => (
                <TableRow key={tag.id}>
                  <TableCell>
                    <span>{tag.name_en}</span>
                    <span className="text-muted-foreground"> / {tag.name_ru}</span>
                    <span className="block font-mono text-xs text-muted-foreground">{tag.slug}</span>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{tag.book_count}</TableCell>
                  <TableCell>
                    <RowActions
                      name={tagName(tag)}
                      onEdit={() => setEditing({ kind: 'tag', tag })}
                      onMerge={() => setEditing({ kind: 'merge-tag', tag })}
                      onDelete={() => deleteTag(tag)}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section aria-labelledby="series-heading" className="space-y-4 min-w-0">
        <div>
          <h2 id="series-heading" className="text-lg">{t('catalogAdmin.seriesTitle')}</h2>
          <p className="text-sm text-muted-foreground">{t('catalogAdmin.seriesDesc')}</p>
        </div>
        <form onSubmit={addSeries} className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2 items-end">
          <div className="space-y-1">
            <Label htmlFor="new-series">{t('catalogAdmin.seriesName')}</Label>
            <Input id="new-series" value={newSeries} maxLength={300} onChange={(e) => setNewSeries(e.target.value)} />
          </div>
          <Button type="submit" disabled={!newSeries.trim()}>
            <Plus className="w-4 h-4 mr-1" aria-hidden="true" />
            {t('catalogAdmin.add')}
          </Button>
        </form>
        <div className="space-y-1">
          <Label htmlFor="series-search">{t('catalogAdmin.findSeries')}</Label>
          <Input id="series-search" type="search" value={seriesQuery} onChange={(e) => setSeriesQuery(e.target.value)} />
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('catalogAdmin.seriesName')}</TableHead>
                <TableHead className="text-right">{t('catalogAdmin.books')}</TableHead>
                <TableHead>{t('admin.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shownSeries.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <span>{item.name}</span>
                    {item.openlibrary_key && (
                      <span className="block font-mono text-xs text-muted-foreground">Open Library {item.openlibrary_key}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{item.book_count}</TableCell>
                  <TableCell>
                    <RowActions
                      name={item.name}
                      onEdit={() => setEditing({ kind: 'series', series: item })}
                      onMerge={() => setEditing({ kind: 'merge-series', series: item })}
                      onDelete={() => deleteSeries(item)}
                    />
                  </TableCell>
                </TableRow>
              ))}
              {shownSeries.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-muted-foreground">
                    {t('catalogAdmin.noSeries')}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          {editing?.kind === 'tag' && (
            <TagEditor
              tag={editing.tag}
              onSave={async (body) => {
                if (finish(await runAction(() => adminApi.updateTag(editing.tag.id, body)), 'catalogAdmin.saved')) {
                  setEditing(null);
                }
              }}
            />
          )}
          {editing?.kind === 'series' && (
            <SeriesEditor
              series={editing.series}
              onSave={async (body) => {
                if (finish(await runAction(() => adminApi.updateSeries(editing.series.id, body)), 'catalogAdmin.saved')) {
                  setEditing(null);
                }
              }}
            />
          )}
          {editing?.kind === 'merge-tag' && (
            <MergeForm
              title={t('catalogAdmin.mergeTagTitle', { name: tagName(editing.tag) })}
              description={t('catalogAdmin.mergeTagDesc')}
              options={sortedTags.filter((tag) => tag.id !== editing.tag.id).map((tag) => ({ id: tag.id, label: tagName(tag) }))}
              onMerge={async (intoId) => {
                if (finish(await runAction(() => adminApi.mergeTag(editing.tag.id, intoId)), 'catalogAdmin.merged')) {
                  setEditing(null);
                }
              }}
            />
          )}
          {editing?.kind === 'merge-series' && (
            <MergeForm
              title={t('catalogAdmin.mergeSeriesTitle', { name: editing.series.name })}
              description={t('catalogAdmin.mergeSeriesDesc')}
              options={series.filter((item) => item.id !== editing.series.id).map((item) => ({ id: item.id, label: item.name }))}
              onMerge={async (intoId) => {
                if (finish(await runAction(() => adminApi.mergeSeries(editing.series.id, intoId)), 'catalogAdmin.merged')) {
                  setEditing(null);
                }
              }}
            />
          )}
        </DialogContent>
      </Dialog>
      {confirmDialog}
    </div>
  );
}

function RowActions({
  name,
  onEdit,
  onMerge,
  onDelete,
}: {
  name: string;
  onEdit: () => void;
  onMerge: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex gap-1">
      <Button size="icon" variant="ghost" onClick={onEdit} aria-label={t('catalogAdmin.editNamed', { name })} title={t('catalogAdmin.edit')}>
        <Pencil className="w-4 h-4" aria-hidden="true" />
      </Button>
      <Button size="icon" variant="ghost" onClick={onMerge} aria-label={t('catalogAdmin.mergeNamed', { name })} title={t('catalogAdmin.merge')}>
        <GitMerge className="w-4 h-4" aria-hidden="true" />
      </Button>
      <Button size="icon" variant="ghost" onClick={onDelete} aria-label={t('catalogAdmin.deleteNamed', { name })} title={t('catalogAdmin.delete')}>
        <Trash2 className="w-4 h-4 text-destructive" aria-hidden="true" />
      </Button>
    </div>
  );
}

function TagEditor({
  tag,
  onSave,
}: {
  tag: TagDto;
  onSave: (body: { name_en: string; name_ru: string }) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [nameEn, setNameEn] = useState(tag.name_en);
  const [nameRu, setNameRu] = useState(tag.name_ru);
  const [saving, setSaving] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    await onSave({ name_en: nameEn.trim(), name_ru: nameRu.trim() });
    setSaving(false);
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>{t('catalogAdmin.editTagTitle')}</DialogTitle>
        <DialogDescription>{t('catalogAdmin.editTagDesc', { slug: tag.slug })}</DialogDescription>
      </DialogHeader>
      <div className="space-y-1">
        <Label htmlFor="edit-tag-en">{t('catalogAdmin.nameEn')}</Label>
        <Input id="edit-tag-en" value={nameEn} maxLength={64} onChange={(e) => setNameEn(e.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="edit-tag-ru">{t('catalogAdmin.nameRu')}</Label>
        <Input id="edit-tag-ru" value={nameRu} maxLength={64} onChange={(e) => setNameRu(e.target.value)} />
      </div>
      <DialogFooter>
        <Button type="submit" disabled={saving || !nameEn.trim() || !nameRu.trim()}>{t('admin.saveChanges')}</Button>
      </DialogFooter>
    </form>
  );
}

function SeriesEditor({
  series,
  onSave,
}: {
  series: SeriesDto;
  onSave: (body: { name: string; description: string }) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(series.name);
  const [description, setDescription] = useState(series.description);
  const [saving, setSaving] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    await onSave({ name: name.trim(), description: description.trim() });
    setSaving(false);
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>{t('catalogAdmin.editSeriesTitle')}</DialogTitle>
        <DialogDescription>{t('catalogAdmin.editSeriesDesc')}</DialogDescription>
      </DialogHeader>
      <div className="space-y-1">
        <Label htmlFor="edit-series-name">{t('catalogAdmin.seriesName')}</Label>
        <Input id="edit-series-name" value={name} maxLength={300} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="edit-series-description">{t('catalogAdmin.seriesDescription')}</Label>
        <Textarea
          id="edit-series-description"
          rows={4}
          maxLength={5000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <DialogFooter>
        <Button type="submit" disabled={saving || !name.trim()}>{t('admin.saveChanges')}</Button>
      </DialogFooter>
    </form>
  );
}

function MergeForm({
  title,
  description,
  options,
  onMerge,
}: {
  title: string;
  description: string;
  options: { id: string; label: string }[];
  onMerge: (intoId: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [intoId, setIntoId] = useState('');
  const [saving, setSaving] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!intoId) return;
    setSaving(true);
    await onMerge(intoId);
    setSaving(false);
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <div className="space-y-1">
        <Label htmlFor="merge-into">{t('catalogAdmin.mergeInto')}</Label>
        <Select value={intoId} onValueChange={setIntoId}>
          <SelectTrigger id="merge-into">
            <SelectValue placeholder={t('catalogAdmin.choose')} />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option.id} value={option.id}>{option.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <DialogFooter>
        <Button type="submit" disabled={saving || !intoId}>{t('catalogAdmin.merge')}</Button>
      </DialogFooter>
    </form>
  );
}
