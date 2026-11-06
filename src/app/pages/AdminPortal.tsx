import { useCallback, useEffect, useState } from 'react';
import { BatchConfig, Book, BookCategory, BookStatus, Order } from '../types';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { Plus, Pencil, Trash2, Users, BookOpen as BookOpenIcon, ClipboardList, CheckCircle2, RotateCcw, Clock, Star } from 'lucide-react';
import { toast } from 'sonner';
import { useCart } from '../contexts/CartContext';
import { useAuth } from '../contexts/AuthContext';
import { useOrders } from '../contexts/OrdersContext';
import { BookDetailsModal } from '../components/BookDetailsModal';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious, PaginationEllipsis } from '../components/ui/pagination';
import { useTranslation } from 'react-i18next';
import { getCategoryTranslation, getStatusTranslation } from '../utils/translations';
import { errorMessage } from '../utils/apiErrors';
import { useCatalog } from '../contexts/CatalogContext';
import { adminApi } from '../../api/endpoints';
import { ActionResult, ApiError, runAction, toApiError } from '../../api/errors';
import { bookFormToDto, bookFromDto } from '../../api/mappers';
import type { BookStatsDto } from '../../api/types';

export default function AdminPortal() {
  const { t } = useTranslation();
  const [books, setBooks] = useState<Book[]>([]);
  const [totalBooks, setTotalBooks] = useState(0);
  const [stats, setStats] = useState<BookStatsDto | null>(null);
  const [booksLoading, setBooksLoading] = useState(true);
  const [booksError, setBooksError] = useState<ApiError | null>(null);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingBook, setEditingBook] = useState<Book | null>(null);
  const { batchConfig, updateBatchConfig } = useCart();
  const [batchDraft, setBatchDraft] = useState<BatchConfig>(batchConfig);
  const { users, updateUserRole, refreshUsers } = useAuth();
  const { orders, confirmOrder, markReturned, cancelOrder, updateDueDate } = useOrders();
  const { invalidateCatalog } = useCatalog();
  const [currentPage, setCurrentPage] = useState(1);
  const booksPerPage = 10;

  useEffect(() => {
    setBatchDraft(batchConfig);
  }, [batchConfig.booksPerBatch, batchConfig.pricePerBatch]);

  const loadBooks = useCallback(async (page: number) => {
    setBooksLoading(true);
    setBooksError(null);
    try {
      const [pageResult, statsResult] = await Promise.all([
        adminApi.listBooks({ page, page_size: booksPerPage, sort: 'created_at' }),
        adminApi.bookStats(),
      ]);
      setBooks(pageResult.items.map(bookFromDto));
      setTotalBooks(pageResult.total);
      setStats(statsResult);
    } catch (e) {
      setBooksError(toApiError(e));
    } finally {
      setBooksLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBooks(currentPage);
  }, [currentPage, loadBooks]);

  function reportResult<T>(result: ActionResult<T>, successKey: string): boolean {
    if (result.ok) {
      toast.success(t(successKey));
      return true;
    }
    toast.error(errorMessage(t, result.error));
    return false;
  }

  const [formData, setFormData] = useState({
    title: '',
    author: '',
    category: 'fiction' as BookCategory,
    ageRange: '',
    status: 'available' as BookStatus,
    coverImage: '',
    images: [] as string[],
    description: '',
    isbn: '',
    publishedYear: new Date().getFullYear()
  });

  const resetForm = () => {
    setFormData({
      title: '',
      author: '',
      category: 'fiction',
      ageRange: '',
      status: 'available',
      coverImage: '',
      images: [],
      description: '',
      isbn: '',
      publishedYear: new Date().getFullYear()
    });
  };

  const handleAddBook = async () => {
    const result = await runAction(() => adminApi.createBook(bookFormToDto(formData)));
    if (!reportResult(result, 'admin.bookAdded')) return;
    setIsAddDialogOpen(false);
    resetForm();
    invalidateCatalog();
    if (currentPage === 1) await loadBooks(1);
    else setCurrentPage(1);
  };

  const handleEditBook = async () => {
    if (!editingBook) return;
    const result = await runAction(() =>
      adminApi.updateBook(editingBook.id, bookFormToDto(formData)),
    );
    if (!reportResult(result, 'admin.bookUpdated')) return;
    setIsEditDialogOpen(false);
    setEditingBook(null);
    resetForm();
    invalidateCatalog();
    await loadBooks(currentPage);
  };

  const handleDeleteBook = async (id: string) => {
    const result = await runAction(() => adminApi.deleteBook(id));
    if (!reportResult(result, 'admin.bookDeleted')) return;
    invalidateCatalog();
    const newTotalPages = Math.ceil((totalBooks - 1) / booksPerPage);
    if (currentPage > newTotalPages && newTotalPages > 0) {
      setCurrentPage(newTotalPages);
    } else {
      await loadBooks(currentPage);
    }
  };

  const handleSaveBatchConfig = async () => {
    const result = await updateBatchConfig(batchDraft);
    reportResult(result, 'admin.configUpdated');
  };

  const openEditDialog = (book: Book) => {
    setEditingBook(book);
    setFormData({
      title: book.title,
      author: book.author,
      category: book.category,
      ageRange: book.ageRange,
      status: book.status,
      coverImage: book.coverImage,
      images: book.images || [book.coverImage],
      description: book.description,
      isbn: book.isbn,
      publishedYear: book.publishedYear
    });
    setIsEditDialogOpen(true);
  };

  const totalPages = Math.ceil(totalBooks / booksPerPage);
  const startIndex = (currentPage - 1) * booksPerPage;
  const endIndex = startIndex + booksPerPage;
  const paginatedBooks = books; // the server returns exactly one page

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleRoleChange = async (userId: string, newRole: 'customer' | 'admin') => {
    const result = await updateUserRole(userId, newRole);
    if (result.ok) {
      toast.success(t('admin.roleUpdated'));
    } else {
      toast.error(`${t('admin.roleUpdateFailed')}: ${errorMessage(t, result.error)}`);
    }
  };

  return (
    <div className="container mx-auto px-4 py-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1>{t('admin.portalTitle')}</h1>
        <Button onClick={() => { resetForm(); setIsAddDialogOpen(true); }}>
          <Plus className="w-4 h-4 mr-2" />
          {t('admin.addBook')}
        </Button>
        <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('admin.addBookTitle')}</DialogTitle>
              <DialogDescription>{t('admin.addBookDesc')}</DialogDescription>
            </DialogHeader>
            <BookForm formData={formData} setFormData={setFormData} t={t} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>{t('admin.cancel')}</Button>
              <Button onClick={handleAddBook}>{t('admin.addBookBtn')}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>{t('admin.batchConfig')}</CardTitle>
            <CardDescription>{t('admin.batchConfigDesc')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="booksPerBatch">{t('admin.booksPerBatch')}</Label>
              <Input
                id="booksPerBatch"
                type="number"
                min="1"
                value={batchDraft.booksPerBatch}
                onChange={(e) => setBatchDraft({ ...batchDraft, booksPerBatch: parseInt(e.target.value) || 5 })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="pricePerBatch">{t('admin.pricePerBatch')}</Label>
              <Input
                id="pricePerBatch"
                type="number"
                min="0"
                step="0.01"
                value={batchDraft.pricePerBatch}
                onChange={(e) => setBatchDraft({ ...batchDraft, pricePerBatch: parseFloat(e.target.value) || 0 })}
              />
            </div>
            <Button onClick={handleSaveBatchConfig}>
              {t('admin.saveConfig')}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('admin.libraryStats')}</CardTitle>
            <CardDescription>{t('admin.libraryStatsDesc')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('admin.totalBooks')}:</span>
              <span>{stats?.total ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('admin.available')}:</span>
              <span>{stats?.available ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('admin.availableSoon')}:</span>
              <span>{stats?.available_soon ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('admin.notAvailable')}:</span>
              <span>{stats?.not_available ?? '—'}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('admin.management')}</CardTitle>
          <CardDescription>{t('admin.managementDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="books" className="w-full">
            <TabsList className="grid w-full grid-cols-3 mb-6">
              <TabsTrigger value="books" className="flex items-center gap-2">
                <BookOpenIcon className="w-4 h-4" />
                {t('admin.booksTab')}
              </TabsTrigger>
              <TabsTrigger value="users" className="flex items-center gap-2">
                <Users className="w-4 h-4" />
                {t('admin.users')}
              </TabsTrigger>
              <TabsTrigger value="orders" className="flex items-center gap-2">
                <ClipboardList className="w-4 h-4" />
                {t('admin.orders')}
                {orders.filter(o => o.status === 'pending').length > 0 && (
                  <Badge className="ml-1 bg-amber-600 text-white text-xs px-1.5 py-0">
                    {orders.filter(o => o.status === 'pending').length}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="books">
          {booksError && (
            <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md mb-4 flex items-center justify-between gap-2">
              <span>{errorMessage(t, booksError)}</span>
              <Button size="sm" variant="outline" onClick={() => loadBooks(currentPage)}>{t('common.retry')}</Button>
            </div>
          )}
          {booksLoading && books.length === 0 && (
            <p className="text-muted-foreground text-sm py-8 text-center">{t('common.loading')}</p>
          )}
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('admin.title')}</TableHead>
                  <TableHead>{t('admin.author')}</TableHead>
                  <TableHead>{t('admin.category')}</TableHead>
                  <TableHead>{t('admin.status')}</TableHead>
                  <TableHead>{t('admin.age')}</TableHead>
                  <TableHead>{t('admin.actions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedBooks.map(book => (
                  <TableRow key={book.id}>
                    <TableCell>{book.title}</TableCell>
                    <TableCell>{book.author}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{getCategoryTranslation(t, book.category)}</Badge>
                    </TableCell>
                    <TableCell>
                      {book.status === 'available' && <Badge className="bg-green-700">{getStatusTranslation(t, book.status)}</Badge>}
                      {book.status === 'available-soon' && <Badge className="bg-amber-700">{getStatusTranslation(t, book.status)}</Badge>}
                      {book.status === 'not-available' && <Badge variant="destructive">{getStatusTranslation(t, book.status)}</Badge>}
                    </TableCell>
                    <TableCell>{book.ageRange}</TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditDialog(book)}
                        >
                          <Pencil className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteBook(book.id)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {totalPages > 1 && (
            <div className="mt-6">
              <Pagination>
                <PaginationContent>
                  <PaginationItem>
                    <PaginationPrevious
                      onClick={() => currentPage > 1 && handlePageChange(currentPage - 1)}
                      className={currentPage === 1 ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
                    />
                  </PaginationItem>

                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => {
                    if (
                      page === 1 ||
                      page === totalPages ||
                      (page >= currentPage - 1 && page <= currentPage + 1)
                    ) {
                      return (
                        <PaginationItem key={page}>
                          <PaginationLink
                            onClick={() => handlePageChange(page)}
                            isActive={currentPage === page}
                            className="cursor-pointer"
                          >
                            {page}
                          </PaginationLink>
                        </PaginationItem>
                      );
                    } else if (page === currentPage - 2 || page === currentPage + 2) {
                      return (
                        <PaginationItem key={page}>
                          <PaginationEllipsis />
                        </PaginationItem>
                      );
                    }
                    return null;
                  })}

                  <PaginationItem>
                    <PaginationNext
                      onClick={() => currentPage < totalPages && handlePageChange(currentPage + 1)}
                      className={currentPage === totalPages ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
                    />
                  </PaginationItem>
                </PaginationContent>
              </Pagination>

              <p className="text-sm text-muted-foreground text-center mt-4">
                {t('admin.showing')} {startIndex + 1}-{Math.min(endIndex, totalBooks)} {t('admin.of')} {totalBooks} {t('admin.books')}
              </p>
            </div>
          )}
            </TabsContent>

            <TabsContent value="users">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('admin.name')}</TableHead>
                  <TableHead>{t('admin.email')}</TableHead>
                  <TableHead>{t('admin.role')}</TableHead>
                  <TableHead>{t('admin.borrowedBooks')}</TableHead>
                  <TableHead>{t('admin.returnDates')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map(user => (
                  <TableRow key={user.id}>
                    <TableCell>{user.name}</TableCell>
                    <TableCell>{user.email}</TableCell>
                    <TableCell>
                      <Select
                        value={user.role}
                        onValueChange={(value: 'customer' | 'admin') => handleRoleChange(user.id, value)}
                      >
                        <SelectTrigger className="w-32">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="customer">{t('admin.customer')}</SelectItem>
                          <SelectItem value="admin">{t('admin.admin')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {user.borrowedBooks.length} {user.borrowedBooks.length !== 1 ? t('admin.books') : t('admin.book')}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {user.borrowedBooks.length > 0 ? (
                        <div className="space-y-1">
                          {user.borrowedBooks.map((borrowed) => {
                            const returnDate = new Date(borrowed.returnDate);
                            const today = new Date();
                            const isOverdue = returnDate < today;
                            const daysLeft = Math.ceil((returnDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

                            return (
                              <div key={borrowed.bookId} className="text-sm">
                                <span className="text-muted-foreground">{borrowed.book.title}:</span>{' '}
                                {isOverdue ? (
                                  <Badge variant="destructive" className="text-xs">
                                    {t('admin.overdueBy')} {Math.abs(daysLeft)} {t('myBooks.days')}
                                  </Badge>
                                ) : daysLeft <= 3 ? (
                                  <Badge className="bg-amber-700 text-xs">
                                    {t('admin.dueIn')} {daysLeft} {t('myBooks.days')}
                                  </Badge>
                                ) : (
                                  <span className="text-xs">{new Date(borrowed.returnDate).toLocaleDateString()}</span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">{t('admin.noBorrowedBooks')}</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
            </TabsContent>

            <TabsContent value="orders">
              <OrdersTab
                orders={orders}
                onConfirm={confirmOrder}
                onMarkReturned={markReturned}
                onCancel={cancelOrder}
                onUpdateDueDate={updateDueDate}
                onChanged={() => {
                  refreshUsers().catch(() => undefined);
                  loadBooks(currentPage);
                }}
                t={t}
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('admin.editBookTitle')}</DialogTitle>
            <DialogDescription>{t('admin.editBookDesc')}</DialogDescription>
          </DialogHeader>
          <BookForm formData={formData} setFormData={setFormData} t={t} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>{t('admin.cancel')}</Button>
            <Button onClick={handleEditBook}>{t('admin.saveChanges')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function BookForm({ formData, setFormData, t }: {
  formData: any;
  setFormData: (data: any) => void;
  t: any;
}) {
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="title">{t('bookForm.title')}</Label>
          <Input
            id="title"
            value={formData.title}
            onChange={(e) => setFormData({ ...formData, title: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="author">{t('bookForm.author')}</Label>
          <Input
            id="author"
            value={formData.author}
            onChange={(e) => setFormData({ ...formData, author: e.target.value })}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="space-y-2">
          <Label htmlFor="category">{t('bookForm.category')}</Label>
          <Select value={formData.category} onValueChange={(value) => setFormData({ ...formData, category: value })}>
            <SelectTrigger id="category">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fiction">{t('categories.fiction')}</SelectItem>
              <SelectItem value="non-fiction">{t('categories.non-fiction')}</SelectItem>
              <SelectItem value="children">{t('categories.children')}</SelectItem>
              <SelectItem value="young-adult">{t('categories.young-adult')}</SelectItem>
              <SelectItem value="science">{t('categories.science')}</SelectItem>
              <SelectItem value="history">{t('categories.history')}</SelectItem>
              <SelectItem value="biography">{t('categories.biography')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="status">{t('bookForm.status')}</Label>
          <Select value={formData.status} onValueChange={(value) => setFormData({ ...formData, status: value })}>
            <SelectTrigger id="status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="available">{t('bookStatus.available')}</SelectItem>
              <SelectItem value="available-soon">{t('bookStatus.availableSoon')}</SelectItem>
              <SelectItem value="not-available">{t('bookStatus.notAvailable')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="ageRange">{t('bookForm.ageRange')}</Label>
          <Input
            id="ageRange"
            placeholder={t('bookForm.ageRangePlaceholder')}
            value={formData.ageRange}
            onChange={(e) => setFormData({ ...formData, ageRange: e.target.value })}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="isbn">{t('bookForm.isbn')}</Label>
          <Input
            id="isbn"
            value={formData.isbn}
            onChange={(e) => setFormData({ ...formData, isbn: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="publishedYear">{t('bookForm.publishedYear')}</Label>
          <Input
            id="publishedYear"
            type="number"
            value={formData.publishedYear}
            onChange={(e) => setFormData({ ...formData, publishedYear: parseInt(e.target.value) })}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="coverImage">{t('bookForm.coverImage')}</Label>
        <Input
          id="coverImage"
          placeholder="https://..."
          value={formData.coverImage}
          onChange={(e) => setFormData({ ...formData, coverImage: e.target.value })}
        />
      </div>

      <div className="space-y-2">
        <Label>{t('bookForm.additionalImages')}</Label>
        <Textarea
          placeholder="https://image1.jpg&#10;https://image2.jpg&#10;https://image3.jpg"
          rows={4}
          value={formData.images?.join('\n') || ''}
          onChange={(e) => {
            const urls = e.target.value.split('\n').filter(url => url.trim());
            setFormData({ ...formData, images: urls });
          }}
        />
        <p className="text-xs text-muted-foreground">
          {t('bookForm.additionalImagesDesc')}
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">{t('bookForm.description')}</Label>
        <Textarea
          id="description"
          rows={4}
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
        />
      </div>
    </div>
  );
}

function orderStatusBadge(status: string, t: any) {
  switch (status) {
    case 'pending':
      return <Badge className="bg-amber-600"><Clock className="w-3 h-3 mr-1" />{t('admin.orderPending')}</Badge>;
    case 'confirmed':
      return <Badge className="bg-blue-700"><CheckCircle2 className="w-3 h-3 mr-1" />{t('admin.orderConfirmed')}</Badge>;
    case 'returned':
      return <Badge className="bg-green-700"><RotateCcw className="w-3 h-3 mr-1" />{t('admin.orderReturned')}</Badge>;
    case 'cancelled':
      return <Badge variant="destructive">{t('admin.orderCancelled')}</Badge>;
  }
}

function dueDateBadge(dueDate: string, status: string, t: any) {
  if (status === 'returned' || status === 'cancelled') return <span className="text-sm text-muted-foreground">—</span>;
  const due = new Date(dueDate);
  const today = new Date();
  const diffDays = Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays < 0) {
    return <Badge variant="destructive" className="text-xs">{t('admin.overdueBy')} {Math.abs(diffDays)} {t('myBooks.days')}</Badge>;
  }
  if (diffDays <= 5) {
    return <Badge className="bg-amber-600 text-xs">{t('admin.dueIn')} {diffDays} {t('myBooks.days')}</Badge>;
  }
  return <span className="text-sm">{due.toLocaleDateString()}</span>;
}

function OrderBooksModal({ order, userContacts, open, onOpenChange, t }: {
  order: Order | null;
  userContacts?: import('../types').UserContacts;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  t: any;
}) {
  const [detailBook, setDetailBook] = useState<Book | null>(null);

  if (!order) return null;
  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t('admin.orderBooksTitle')} #{order.id.slice(-6).toUpperCase()}
            </DialogTitle>
            <DialogDescription>
              {order.userName} · {order.userEmail}
            </DialogDescription>
            {userContacts && (
              <div className="flex gap-2 flex-wrap text-xs text-muted-foreground pt-0.5">
                {userContacts.whatsapp && <span>WhatsApp: {userContacts.whatsapp}</span>}
                {userContacts.telegram && <span>Telegram: {userContacts.telegram}</span>}
                {userContacts.instagram && <span>Instagram: {userContacts.instagram}</span>}
                {userContacts.phone && <span>{t('auth.phone')}: {userContacts.phone}</span>}
              </div>
            )}
          </DialogHeader>

          <div className="flex gap-3 flex-wrap py-1">
            {orderStatusBadge(order.status, t)}
            <Badge variant="outline">{order.books.length} {t('cart.books')}</Badge>
            <span className="text-sm text-muted-foreground">{t('admin.orderedAt')}: {new Date(order.orderedAt).toLocaleDateString()}</span>
            {order.status !== 'returned' && (
              <span className="text-sm text-muted-foreground">{t('admin.dueDate')}: {new Date(order.dueDate).toLocaleDateString()}</span>
            )}
            {order.returnedAt && (
              <span className="text-sm text-muted-foreground">{t('admin.returnedOn')} {new Date(order.returnedAt).toLocaleDateString()}</span>
            )}
          </div>

          <div className="divide-y divide-border">
            {order.books.map((book, idx) => (
              <div key={book.id} className="flex gap-4 py-3 items-center">
                <span className="text-xs text-muted-foreground w-5 shrink-0">{idx + 1}.</span>
                <button
                  className="w-10 h-14 shrink-0 overflow-hidden rounded bg-muted hover:ring-2 hover:ring-primary transition-all"
                  onClick={() => setDetailBook(book)}
                >
                  <img src={book.coverImage} alt={book.title} className="w-full h-full object-cover" />
                </button>
                <div className="flex-1 min-w-0">
                  <button
                    className="font-medium leading-tight truncate text-left hover:text-primary hover:underline underline-offset-2 transition-colors w-full"
                    onClick={() => setDetailBook(book)}
                  >
                    {book.title}
                  </button>
                  <p className="text-sm text-muted-foreground">{book.author}</p>
                  <div className="flex gap-1.5 mt-1 flex-wrap">
                    <Badge variant="outline" className="text-xs">{book.category}</Badge>
                    <Badge variant="outline" className="text-xs">{book.ageRange}</Badge>
                    {book.isbn && <span className="text-xs text-muted-foreground font-mono">ISBN {book.isbn}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <BookDetailsModal
        book={detailBook}
        open={!!detailBook}
        onOpenChange={open => { if (!open) setDetailBook(null); }}
      />
    </>
  );
}

function OrdersTab({
  orders,
  onConfirm,
  onMarkReturned,
  onCancel,
  onUpdateDueDate,
  onChanged,
  t,
}: {
  orders: Order[];
  onConfirm: (id: string) => Promise<ActionResult>;
  onMarkReturned: (id: string) => Promise<ActionResult>;
  onCancel: (id: string) => Promise<ActionResult>;
  onUpdateDueDate: (id: string, date: string) => Promise<ActionResult>;
  onChanged: () => void;
  t: any;
}) {
  const { users } = useAuth();
  const [busyOrderId, setBusyOrderId] = useState<string | null>(null);

  const runOrderAction = async (
    orderId: string,
    action: () => Promise<ActionResult>,
    successKey: string,
  ) => {
    setBusyOrderId(orderId);
    const result = await action();
    setBusyOrderId(null);
    if (result.ok) {
      toast.success(t(successKey));
      onChanged();
    } else {
      toast.error(errorMessage(t, result.error));
    }
  };
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'confirmed' | 'returned' | 'cancelled'>('all');
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [editingDueDateId, setEditingDueDateId] = useState<string | null>(null);
  const [dueDateInput, setDueDateInput] = useState('');

  const selectedUserContacts = selectedOrder
    ? users.find(u => u.id === selectedOrder.userId)?.contacts ?? selectedOrder.contacts
    : undefined;

  const filtered = statusFilter === 'all' ? orders : orders.filter(o => o.status === statusFilter);

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        {(['all', 'pending', 'confirmed', 'returned', 'cancelled'] as const).map(s => (
          <Button
            key={s}
            size="sm"
            variant={statusFilter === s ? 'default' : 'outline'}
            onClick={() => setStatusFilter(s)}
          >
            {t(`admin.filter${s.charAt(0).toUpperCase() + s.slice(1)}`)}
            {s !== 'all' && (
              <span className="ml-1 opacity-70">({orders.filter(o => o.status === s).length})</span>
            )}
          </Button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="text-muted-foreground text-sm py-8 text-center">{t('admin.noOrders')}</p>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('admin.orderId')}</TableHead>
                <TableHead>{t('admin.customer')}</TableHead>
                <TableHead>{t('admin.orderBooks')}</TableHead>
                <TableHead>{t('admin.orderStatus')}</TableHead>
                <TableHead>{t('admin.orderedAt')}</TableHead>
                <TableHead>{t('admin.dueDate')}</TableHead>
                <TableHead>{t('admin.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map(order => (
                <TableRow
                  key={order.id}
                  className="cursor-pointer hover:bg-muted/60"
                  onClick={() => setSelectedOrder(order)}
                >
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    #{order.id.slice(-6).toUpperCase()}
                  </TableCell>
                  <TableCell>
                    {(() => {
                      const u = users.find(u => u.id === order.userId);
                      const contacts = u?.contacts ?? order.contacts;
                      const pref = contacts?.preferred;
                      const prefValue = pref ? contacts?.[pref] : undefined;
                      return (
                        <div>
                          <p className="font-medium">{order.userName}</p>
                          <p className="text-xs text-muted-foreground">{order.userEmail}</p>
                          {pref && prefValue && (
                            <div className="flex items-center gap-1 mt-0.5">
                              <Star className="w-3 h-3 fill-amber-400 text-amber-400 shrink-0" />
                              <span className="text-xs text-muted-foreground">{t(`auth.${pref}`)}: {prefValue}</span>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      <Badge variant="outline" className="w-fit">{order.books.length} {t('cart.books')}</Badge>
                      <div className="text-xs text-muted-foreground space-y-0.5 max-w-[200px]">
                        {order.books.slice(0, 2).map(b => (
                          <p key={b.id} className="truncate">{b.title}</p>
                        ))}
                        {order.books.length > 2 && (
                          <p className="text-primary underline-offset-2 hover:underline">+{order.books.length - 2} {t('admin.more')}</p>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{orderStatusBadge(order.status, t)}</TableCell>
                  <TableCell className="text-sm">{new Date(order.orderedAt).toLocaleDateString()}</TableCell>
                  <TableCell onClick={e => e.stopPropagation()}>
                    {order.status === 'returned' || order.status === 'cancelled' ? (
                      <span className="text-sm text-muted-foreground">—</span>
                    ) : editingDueDateId === order.id ? (
                      <div className="flex gap-1 items-center">
                        <input
                          type="date"
                          value={dueDateInput}
                          onChange={e => setDueDateInput(e.target.value)}
                          className="border border-border rounded px-2 py-1 text-sm bg-background"
                        />
                        <Button size="sm" className="h-7 px-2" onClick={() => {
                          if (dueDateInput) runOrderAction(order.id, () => onUpdateDueDate(order.id, dueDateInput), 'admin.dueDateUpdated');
                          setEditingDueDateId(null);
                        }}>✓</Button>
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setEditingDueDateId(null)}>✕</Button>
                      </div>
                    ) : (
                      <button
                        className="flex items-center gap-1 text-sm hover:text-primary hover:underline underline-offset-2 transition-colors group"
                        onClick={() => { setEditingDueDateId(order.id); setDueDateInput(order.dueDate); }}
                      >
                        {dueDateBadge(order.dueDate, order.status, t)}
                        <Pencil className="w-3 h-3 opacity-0 group-hover:opacity-60 transition-opacity" />
                      </button>
                    )}
                  </TableCell>
                  <TableCell onClick={e => e.stopPropagation()}>
                    <div className="flex gap-2 flex-wrap">
                      {order.status === 'pending' && (
                        <>
                          <Button
                            size="sm"
                            disabled={busyOrderId === order.id}
                            onClick={() => runOrderAction(order.id, () => onConfirm(order.id), 'admin.orderConfirmedMsg')}
                          >
                            <CheckCircle2 className="w-4 h-4 mr-1" />
                            {t('admin.confirmOrder')}
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={busyOrderId === order.id}
                            onClick={() => runOrderAction(order.id, () => onCancel(order.id), 'admin.orderCancelledMsg')}
                          >
                            {t('admin.cancelOrder')}
                          </Button>
                        </>
                      )}
                      {order.status === 'confirmed' && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyOrderId === order.id}
                          onClick={() => runOrderAction(order.id, () => onMarkReturned(order.id), 'admin.orderReturnedMsg')}
                        >
                          <RotateCcw className="w-4 h-4 mr-1" />
                          {t('admin.markReturned')}
                        </Button>
                      )}
                      {order.status === 'returned' && (
                        <span className="text-xs text-muted-foreground">
                          {t('admin.returnedOn')} {order.returnedAt ? new Date(order.returnedAt).toLocaleDateString() : '—'}
                        </span>
                      )}
                      {order.status === 'cancelled' && (
                        <span className="text-xs text-muted-foreground">{t('admin.orderCancelled')}</span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <OrderBooksModal
        order={selectedOrder}
        userContacts={selectedUserContacts}
        open={!!selectedOrder}
        onOpenChange={open => { if (!open) setSelectedOrder(null); }}
        t={t}
      />
    </div>
  );
}
