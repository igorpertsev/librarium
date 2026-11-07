import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';
import { ThumbsUp } from 'lucide-react';
import { toast } from 'sonner';
import { purchasesApi } from '../../api/endpoints';
import { runAction } from '../../api/errors';
import type { PurchaseRequestDto } from '../../api/types';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { errorMessage } from '../utils/apiErrors';

/** Readers suggest books for the library to buy and vote for each other's suggestions. */
export default function Suggestions() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const [items, setItems] = useState<PurchaseRequestDto[] | null>(null);
  const [title, setTitle] = useState(params.get('title') ?? '');
  const [author, setAuthor] = useState('');
  const [isbn, setIsbn] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = `${t('suggest.title')} — Little Dragon`;
  }, [t]);

  const load = useCallback(async () => {
    setItems(await purchasesApi.list().catch(() => []));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const replace = (updated: PurchaseRequestDto) =>
    setItems((current) => current?.map((item) => (item.id === updated.id ? updated : item)) ?? current);

  const submit = async () => {
    setBusy(true);
    const result = await runAction(() =>
      purchasesApi.suggest({ title, author, isbn: isbn.trim() || null, note: note.trim() || null }),
    );
    setBusy(false);
    if (!result.ok) {
      toast.error(errorMessage(t, result.error));
      return;
    }
    toast.success(result.data.created ? t('suggest.created') : t('suggest.merged'));
    setTitle('');
    setAuthor('');
    setIsbn('');
    setNote('');
    await load();
  };

  const toggleVote = async (item: PurchaseRequestDto) => {
    const result = await runAction(() => (item.voted ? purchasesApi.unvote(item.id) : purchasesApi.vote(item.id)));
    if (result.ok) replace(result.data);
    else toast.error(errorMessage(t, result.error));
  };

  return (
    <div className="container mx-auto px-4 py-8 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl mb-1">{t('suggest.title')}</h1>
        <p className="text-muted-foreground">{t('suggest.description')}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('suggest.formTitle')}</CardTitle>
          <CardDescription>{t('suggest.formHint')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="suggest-title">{t('bookForm.title')}</Label>
              <Input id="suggest-title" required maxLength={500} value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="suggest-author">{t('bookForm.author')}</Label>
              <Input id="suggest-author" required maxLength={300} value={author} onChange={(e) => setAuthor(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="suggest-isbn">{t('suggest.isbn')}</Label>
              <Input id="suggest-isbn" inputMode="numeric" maxLength={20} value={isbn} onChange={(e) => setIsbn(e.target.value)} />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="suggest-note">{t('suggest.note')}</Label>
              <Textarea id="suggest-note" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={busy || !title.trim() || !author.trim()}>
                {t('suggest.submit')}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <section aria-labelledby="suggestions-title" className="space-y-3">
        <h2 id="suggestions-title" className="text-lg">{t('suggest.listTitle')}</h2>
        {items === null ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('suggest.empty')}</p>
        ) : (
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id} className="flex items-start gap-3 rounded-lg border border-border p-3">
                <Button
                  variant={item.voted ? 'default' : 'outline'}
                  size="sm"
                  aria-pressed={item.voted}
                  aria-label={item.voted ? t('suggest.unvote', { title: item.title }) : t('suggest.vote', { title: item.title })}
                  onClick={() => void toggleVote(item)}
                  className="shrink-0 tabular-nums"
                >
                  <ThumbsUp className="w-4 h-4 mr-1" aria-hidden="true" />
                  {item.votes}
                </Button>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{item.title}</p>
                  <p className="text-sm text-muted-foreground">{item.author}</p>
                  {item.note && <p className="text-sm mt-1">{item.note}</p>}
                  {item.librarian_note && (
                    <p className="text-sm mt-1 text-primary">{t('suggest.libraryNote', { note: item.librarian_note })}</p>
                  )}
                </div>
                <Badge variant={item.status === 'ordered' ? 'default' : 'outline'} className="shrink-0">
                  {t(`suggest.status.${item.status}`)}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
