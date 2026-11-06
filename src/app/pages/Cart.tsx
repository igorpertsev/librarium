import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useCart } from '../contexts/CartContext';
import { useAuth } from '../contexts/AuthContext';
import { useOrders } from '../contexts/OrdersContext';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Separator } from '../components/ui/separator';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { ShoppingCart, Trash2, X, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { errorMessage } from '../utils/apiErrors';
import { useCatalog } from '../contexts/CatalogContext';
import type { ActionResult } from '../../api/errors';

export default function Cart() {
  const { t } = useTranslation();
  const {
    cart,
    batchConfig,
    removeBookFromCart: removeBookRequest,
    removeBatch: removeBatchRequest,
    getTotalPrice,
    refreshCart,
    unavailableBookIds,
    isLoading,
    error,
  } = useCart();
  const { user } = useAuth();
  const { placeOrder } = useOrders();
  const { invalidateCatalog } = useCatalog();
  const [showCheckoutDialog, setShowCheckoutDialog] = useState(false);
  const [orderComplete, setOrderComplete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const reportFailure = (result: ActionResult) => {
    if (!result.ok) toast.error(errorMessage(t, result.error));
  };
  const removeBookFromCart = async (batchId: string, bookId: string) =>
    reportFailure(await removeBookRequest(batchId, bookId));
  const removeBatch = async (batchId: string) => reportFailure(await removeBatchRequest(batchId));

  const handleCheckout = () => {
    setShowCheckoutDialog(true);
  };

  const confirmCheckout = async () => {
    if (!user || submitting) return;
    setSubmitting(true);
    // The server builds the order from its copy of the cart and computes the total.
    const result = await placeOrder();
    setSubmitting(false);
    if (!result.ok) {
      // 409 BOOK_UNAVAILABLE: nothing was created; show which books and resync.
      setShowCheckoutDialog(false);
      toast.error(errorMessage(t, result.error));
      invalidateCatalog();
      await refreshCart();
      return;
    }
    setOrderComplete(true);
    setTimeout(() => {
      // Resync after the confirmation: ordered books left the cart, an incomplete batch stays.
      // (Refreshing earlier would empty the cart and unmount this dialog.)
      refreshCart();
      setShowCheckoutDialog(false);
      setOrderComplete(false);
      toast.success(t('cart.checkoutSuccess'));
      navigate('/');
    }, 2000);
  };

  const totalPrice = getTotalPrice();
  const completeBatches = cart.filter(batch => batch.books.length === batchConfig.booksPerBatch);
  const incompleteBatches = cart.filter(batch => batch.books.length < batchConfig.booksPerBatch);

  if (cart.length === 0 && (isLoading || error)) {
    return (
      <div className="container mx-auto px-4 py-12 text-center space-y-3">
        {isLoading ? (
          <p className="text-muted-foreground">{t('common.loading')}</p>
        ) : error ? (
          <>
            <p className="text-destructive">{errorMessage(t, error)}</p>
            <Button variant="outline" onClick={() => refreshCart()}>{t('common.retry')}</Button>
          </>
        ) : null}
      </div>
    );
  }

  if (cart.length === 0) {
    return (
      <div className="container mx-auto px-4 py-12">
        <Card className="max-w-md mx-auto text-center">
          <CardContent className="pt-12 pb-8">
            <div className="flex justify-center mb-4">
              <div className="p-4 bg-muted rounded-full">
                <ShoppingCart className="w-12 h-12 text-muted-foreground" />
              </div>
            </div>
            <h2 className="mb-2">{t('cart.empty')}</h2>
            <p className="text-muted-foreground mb-6">
              {t('cart.startBrowsing')}
            </p>
            <Button onClick={() => navigate('/')}>
              {t('cart.browseBooks')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6">
      <h1 className="mb-6">{t('cart.title')}</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {incompleteBatches.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t('cart.incompleteBatches')}</CardTitle>
                <CardDescription>
                  {t('cart.addMoreBooks', { count: batchConfig.booksPerBatch - incompleteBatches[0].books.length })}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {incompleteBatches.map(batch => (
                  <div key={batch.batchId} className="space-y-3">
                    <div className="flex justify-between items-center">
                      <Badge variant="outline">
                        {batch.books.length} / {batchConfig.booksPerBatch} {t('cart.books')}
                      </Badge>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeBatch(batch.batchId)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                    {batch.books.map(book => (
                      <div key={book.id} className="flex gap-3 p-3 bg-muted rounded-lg">
                        <div className="w-12 h-16 flex-shrink-0 overflow-hidden rounded bg-background">
                          <img
                            src={book.coverImage}
                            alt={book.title}
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="truncate">{book.title}</p>
                          <p className="text-sm text-muted-foreground truncate">{book.author}</p>
                          {unavailableBookIds.has(book.id) && (
                            <Badge variant="destructive" className="mt-1">{t('cart.unavailable')}</Badge>
                          )}
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeBookFromCart(batch.batchId, book.id)}
                        >
                          <X className="w-4 h-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {completeBatches.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>{t('cart.completeBatches')}</CardTitle>
                <CardDescription>{t('cart.completeBatchesDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {completeBatches.map((batch, index) => (
                  <div key={batch.batchId} className="space-y-3">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <Badge className="bg-green-700">{t('cart.batch')} {index + 1}</Badge>
                        <Badge variant="outline">
                          {batch.books.length} {t('cart.books')}
                        </Badge>
                        <span className="text-sm">${batchConfig.pricePerBatch.toFixed(2)}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeBatch(batch.batchId)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                    <div className="grid grid-cols-5 gap-2">
                      {batch.books.map(book => (
                        <div
                          key={book.id}
                          className="relative group aspect-[3/4] overflow-hidden rounded bg-muted"
                        >
                          <img
                            src={book.coverImage}
                            alt={book.title}
                            className={`w-full h-full object-cover ${unavailableBookIds.has(book.id) ? 'opacity-40' : ''}`}
                          />
                          {unavailableBookIds.has(book.id) && (
                            <Badge variant="destructive" className="absolute bottom-1 left-1 text-[10px] px-1 py-0">
                              {t('cart.unavailable')}
                            </Badge>
                          )}
                          <button
                            onClick={() => removeBookFromCart(batch.batchId, book.id)}
                            className="absolute top-1 right-1 p-1 bg-destructive rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <X className="w-3 h-3 text-destructive-foreground" />
                          </button>
                        </div>
                      ))}
                    </div>
                    {index < completeBatches.length - 1 && <Separator />}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>

        <div>
          <Card className="sticky top-24">
            <CardHeader>
              <CardTitle>{t('cart.summary')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{t('cart.completeBatches')}</span>
                  <span>{completeBatches.length}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{t('cart.incompleteBatches')}</span>
                  <span>{incompleteBatches.length}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{t('cart.pricePerBatchLabel')}</span>
                  <span>${batchConfig.pricePerBatch.toFixed(2)}</span>
                </div>
                <Separator />
                <div className="flex justify-between">
                  <span>{t('cart.total')}</span>
                  <span className="text-xl">${totalPrice.toFixed(2)}</span>
                </div>
              </div>

              {incompleteBatches.length > 0 && (
                <div className="text-sm text-muted-foreground bg-muted p-3 rounded-md">
                  {t('cart.incompleteBatchNote')}
                </div>
              )}

              {unavailableBookIds.size > 0 && (
                <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">
                  {t('cart.unavailableNote')}
                </div>
              )}
            </CardContent>
            <CardFooter className="flex flex-col gap-2">
              <Button
                className="w-full"
                onClick={handleCheckout}
                disabled={completeBatches.length === 0}
              >
                {t('cart.checkout')}
              </Button>
              <Button
                variant="outline"
                className="w-full"
                onClick={() => navigate('/')}
              >
                {t('cart.continueShopping')}
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>

      <Dialog open={showCheckoutDialog} onOpenChange={setShowCheckoutDialog}>
        <DialogContent>
          {!orderComplete ? (
            <>
              <DialogHeader>
                <DialogTitle>Confirm Order</DialogTitle>
                <DialogDescription>
                  Review your order before placing it
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Batches</span>
                    <span>{completeBatches.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Total Books</span>
                    <span>{completeBatches.length * batchConfig.booksPerBatch}</span>
                  </div>
                  <Separator />
                  <div className="flex justify-between">
                    <span>Total Amount</span>
                    <span>${totalPrice.toFixed(2)}</span>
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowCheckoutDialog(false)}>
                  Cancel
                </Button>
                <Button onClick={confirmCheckout} disabled={submitting}>
                  Place Order
                </Button>
              </DialogFooter>
            </>
          ) : (
            <div className="text-center py-8">
              <div className="flex justify-center mb-4">
                <div className="p-4 bg-green-100 dark:bg-green-900 rounded-full">
                  <CheckCircle2 className="w-12 h-12 text-green-700 dark:text-green-300" />
                </div>
              </div>
              <h2 className="mb-2">Order Placed!</h2>
              <p className="text-muted-foreground">
                Your order has been successfully placed.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
