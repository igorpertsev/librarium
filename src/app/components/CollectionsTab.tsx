import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, Award, Plus, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { adminApi, booksApi, collectionsApi, libraryApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { BookDto, BookPickDto, CollectionDto, CollectionSummaryDto } from '../../api/types';
import { errorMessage } from '../utils/apiErrors';
import { useCollectionText } from '../utils/collections';
import { invalidateLibraryRules } from '../utils/useLibraryRules';
import { useConfirm } from './ConfirmDialog';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Textarea } from './ui/textarea';

/** Search the catalogue and pick a title. */
function BookPicker({ id, label, onPick }: { id: string; label: string; onPick: (book: BookDto) => void }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<BookDto[]>([]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      booksApi
        .list({ q: query.trim(), page: 1, page_size: 8 }, controller.signal)
        .then((page) => setResults(page.items), () => undefined);
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="search" placeholder={t('collections.searchPlaceholder')} value={query} onChange={(e) => setQuery(e.target.value)} />
      {results.length > 0 && (
        <ul className="rounded-md border border-border divide-y divide-border" aria-label={t('collections.results')}>
          {results.map((book) => (
            <li key={book.id} className="flex items-center justify-between gap-2 px-2 py-1 text-sm">
              <span className="min-w-0 truncate">
                {book.title} <span className="text-muted-foreground">· {book.author}</span>
              </span>
              <Button type="button" size="sm" variant="ghost" onClick={() => { onPick(book); setQuery(''); }} aria-label={t('collections.addNamed', { title: book.title })}>
                <Plus className="w-4 h-4" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PickEditor() {
  const { t } = useTranslation();
  const [pick, setPick] = useState<BookPickDto | null>(null);
  const [book, setBook] = useState<{ id: string; title: string } | null>(null);
  const [noteEn, setNoteEn] = useState('');
  const [noteRu, setNoteRu] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    libraryApi.pick().then((found) => {
      setPick(found);
      if (found) {
        setBook({ id: found.book.id, title: found.book.title });
        setNoteEn(found.note_en ?? '');
        setNoteRu(found.note_ru ?? '');
      }
    }, () => undefined);
  }, []);

  const save = async () => {
    if (!book) return;
    setBusy(true);
    const result = await runAction(() => adminApi.setPick({ book_id: book.id, note_en: noteEn.trim() || null, note_ru: noteRu.trim() || null }));
    setBusy(false);
    if (result.ok) {
      setPick(result.data);
      invalidateLibraryRules();
      toast.success(t('collections.pickSaved'));
    } else toast.error(errorMessage(t, result.error));
  };

  const clear = async () => {
    setBusy(true);
    const result = await runAction(() => adminApi.clearPick());
    setBusy(false);
    if (result.ok) {
      setPick(null);
      setBook(null);
      setNoteEn('');
      setNoteRu('');
      invalidateLibraryRules();
      toast.success(t('collections.pickCleared'));
    } else toast.error(errorMessage(t, result.error));
  };

  return (
    <section aria-labelledby="pick-editor" className="rounded-lg border border-border p-4 space-y-3">
      <h2 id="pick-editor" className="flex items-center gap-2 text-lg">
        <Award className="w-5 h-5 text-primary" aria-hidden="true" />
        {t('collections.bookOfTheMonth')}
      </h2>
      <p className="text-sm">{book ? t('collections.pickChosen', { title: book.title }) : t('collections.pickNone')}</p>
      <BookPicker id="pick-search" label={t('collections.pickChoose')} onPick={(found) => setBook({ id: found.id, title: found.title })} />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="pick-note-en">{t('collections.noteEn')}</Label>
          <Textarea id="pick-note-en" rows={2} maxLength={500} value={noteEn} onChange={(e) => setNoteEn(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="pick-note-ru">{t('collections.noteRu')}</Label>
          <Textarea id="pick-note-ru" rows={2} maxLength={500} value={noteRu} onChange={(e) => setNoteRu(e.target.value)} />
        </div>
      </div>
      <div className="flex gap-2">
        <Button onClick={save} disabled={busy || !book}>{t('collections.pickSave')}</Button>
        {pick && <Button variant="ghost" onClick={clear} disabled={busy}>{t('collections.pickClear')}</Button>}
      </div>
    </section>
  );
}

/** Admin: the book of the month and the librarians' collections. */
export function CollectionsTab() {
  const { t } = useTranslation();
  const textOf = useCollectionText();
  const { confirm, confirmDialog } = useConfirm();
  const [list, setList] = useState<CollectionSummaryDto[] | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [open, setOpen] = useState<CollectionDto | null>(null);
  const [books, setBooks] = useState<{ id: string; title: string }[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setList(await collectionsApi.list().catch(() => []));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const edit = async (slug: string) => {
    const found = await collectionsApi.get(slug).catch(() => null);
    setOpen(found);
    setBooks(found ? found.books.map((b) => ({ id: b.id, title: b.title })) : []);
  };

  const run = async <T,>(action: () => Promise<T>, done?: string): Promise<T | null> => {
    setBusy(true);
    const result = await runAction(action);
    setBusy(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return null;
    }
    if (done) toast.success(done);
    return result.data;
  };

  const create = async () => {
    const made = await run(() => adminApi.createCollection({ title_en: newTitle, description_en: '', featured: false, position: 0 }), t('collections.created'));
    if (made) {
      setNewTitle('');
      await load();
      await edit(made.slug);
    }
  };

  const saveDetails = async () => {
    if (!open) return;
    const saved = await run(
      () =>
        adminApi.updateCollection(open.id, {
          title_en: open.title_en,
          title_ru: open.title_ru?.trim() || null,
          description_en: open.description_en,
          description_ru: open.description_ru?.trim() || null,
          slug: open.slug,
          featured: open.featured,
          position: open.position,
        }),
      t('collections.saved'),
    );
    if (saved) {
      setOpen({ ...open, ...saved });
      await load();
    }
  };

  const saveBooks = async () => {
    if (!open) return;
    const saved = await run(() => adminApi.setCollectionBooks(open.id, books.map((b) => b.id)), t('collections.booksSaved'));
    if (saved) {
      setBooks(saved.books.map((b) => ({ id: b.id, title: b.title })));
      await load();
    }
  };

  const remove = async (collection: CollectionSummaryDto) => {
    const ok = await confirm({
      title: t('collections.deleteTitle', { title: textOf(collection).title }),
      description: t('collections.deleteDesc'),
      confirmLabel: t('collections.delete'),
      destructive: true,
    });
    if (!ok) return;
    if (await run(() => adminApi.deleteCollection(collection.id)) !== null) {
      if (open?.id === collection.id) setOpen(null);
      await load();
    }
  };

  const move = (index: number, by: number) =>
    setBooks((current) => {
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(index + by, 0, item);
      return next;
    });

  return (
    <div className="space-y-6">
      <PickEditor />

      <section aria-labelledby="collections-title" className="space-y-3">
        <h2 id="collections-title" className="text-lg">{t('collections.title')}</h2>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void create();
          }}
        >
          <div className="space-y-2 flex-1 min-w-48">
            <Label htmlFor="new-collection">{t('collections.newTitle')}</Label>
            <Input id="new-collection" maxLength={200} value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
          </div>
          <Button type="submit" disabled={busy || !newTitle.trim()}>
            <Plus className="w-4 h-4 mr-1" aria-hidden="true" />
            {t('collections.create')}
          </Button>
        </form>
        {list === null ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : list.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('collections.none')}</p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {list.map((collection) => (
              <li key={collection.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <div className="min-w-0">
                  <p className="font-medium">{textOf(collection).title}</p>
                  <p className="text-sm text-muted-foreground">
                    /collections/{collection.slug} · {t('collections.bookCount', { count: collection.book_count })}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {collection.featured && <Badge>{t('collections.featured')}</Badge>}
                  <Button size="sm" variant="outline" onClick={() => edit(collection.slug)} aria-label={t('collections.editNamed', { title: textOf(collection).title })}>
                    {t('collections.edit')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => remove(collection)} aria-label={t('collections.deleteNamed', { title: textOf(collection).title })}>
                    <Trash2 className="w-4 h-4" aria-hidden="true" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {open && (
        <section aria-labelledby="collection-editor" className="rounded-lg border border-border p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h2 id="collection-editor" className="text-lg">{textOf(open).title}</h2>
            <Button size="sm" variant="ghost" onClick={() => setOpen(null)} aria-label={t('collections.close')}>
              <X className="w-4 h-4" aria-hidden="true" />
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="collection-title-en">{t('collections.titleEn')}</Label>
              <Input id="collection-title-en" maxLength={200} value={open.title_en} onChange={(e) => setOpen({ ...open, title_en: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="collection-title-ru">{t('collections.titleRu')}</Label>
              <Input id="collection-title-ru" maxLength={200} value={open.title_ru ?? ''} onChange={(e) => setOpen({ ...open, title_ru: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="collection-desc-en">{t('collections.descriptionEn')}</Label>
              <Textarea id="collection-desc-en" rows={2} maxLength={5000} value={open.description_en} onChange={(e) => setOpen({ ...open, description_en: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="collection-desc-ru">{t('collections.descriptionRu')}</Label>
              <Textarea id="collection-desc-ru" rows={2} maxLength={5000} value={open.description_ru ?? ''} onChange={(e) => setOpen({ ...open, description_ru: e.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="collection-slug">{t('collections.slug')}</Label>
              <Input id="collection-slug" maxLength={80} pattern="[A-Za-z0-9-]+" value={open.slug} onChange={(e) => setOpen({ ...open, slug: e.target.value })} />
            </div>
            <div className="flex items-end gap-6">
              <div className="space-y-2">
                <Label htmlFor="collection-position">{t('collections.position')}</Label>
                <Input id="collection-position" type="number" min={0} max={1000} className="w-24" value={open.position} onChange={(e) => setOpen({ ...open, position: Number(e.target.value) || 0 })} />
              </div>
              <div className="flex items-center gap-2 pb-2">
                <Switch id="collection-featured" checked={open.featured} onCheckedChange={(featured) => setOpen({ ...open, featured })} />
                <Label htmlFor="collection-featured">{t('collections.featuredLabel')}</Label>
              </div>
            </div>
          </div>
          <Button onClick={saveDetails} disabled={busy || !open.title_en.trim()}>{t('collections.saveDetails')}</Button>

          <div className="space-y-2">
            <h3 className="font-medium">{t('collections.booksTitle')}</h3>
            {books.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('collections.noBooks')}</p>
            ) : (
              <ol className="space-y-1">
                {books.map((book, index) => (
                  <li key={book.id} className="flex items-center gap-2 text-sm">
                    <span className="w-6 text-muted-foreground tabular-nums">{index + 1}.</span>
                    <span className="flex-1 min-w-0 truncate">{book.title}</span>
                    <Button size="sm" variant="ghost" disabled={index === 0} onClick={() => move(index, -1)} aria-label={t('collections.moveUp', { title: book.title })}>
                      <ArrowUp className="w-4 h-4" aria-hidden="true" />
                    </Button>
                    <Button size="sm" variant="ghost" disabled={index === books.length - 1} onClick={() => move(index, 1)} aria-label={t('collections.moveDown', { title: book.title })}>
                      <ArrowDown className="w-4 h-4" aria-hidden="true" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setBooks((current) => current.filter((b) => b.id !== book.id))} aria-label={t('collections.removeNamed', { title: book.title })}>
                      <X className="w-4 h-4" aria-hidden="true" />
                    </Button>
                  </li>
                ))}
              </ol>
            )}
            <BookPicker
              id="collection-book-search"
              label={t('collections.addBooks')}
              onPick={(found) =>
                setBooks((current) => (current.some((b) => b.id === found.id) ? current : [...current, { id: found.id, title: found.title }]))
              }
            />
            <Button onClick={saveBooks} disabled={busy}>{t('collections.saveBooks')}</Button>
          </div>
        </section>
      )}
      {confirmDialog}
    </div>
  );
}
