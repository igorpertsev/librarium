import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useOrders } from '../contexts/OrdersContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Calendar, CalendarPlus, Mail, User as UserIcon, BookOpen, Pencil, MessageCircle, Star, Clock } from 'lucide-react';
import { UserContacts, PreferredContact } from '../types';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { errorMessage } from '../utils/apiErrors';
import { daysUntil, useFormat } from '../utils/format';
import { useConfirm } from '../components/ConfirmDialog';
import { orderLabel } from '../utils/translations';
import { useLibraryRules } from '../utils/useLibraryRules';
import { LateReturnsCard } from '../components/LateReturnsCard';
import { PickupLine } from '../components/PickupLine';
import { ReservationsCard } from '../components/ReservationsCard';
import { ReadingLogCard } from '../components/ReadingLogCard';
import { useWaitlist } from '../contexts/WaitlistContext';
import { WaitlistButton } from '../components/WaitlistButton';
import { ReadingListCard } from '../components/ReadingListCard';
import { NextInSeriesCard } from '../components/NextInSeriesCard';
import { HeldForYouCard } from '../components/HeldForYouCard';
import { ExtendFromLink } from '../components/ExtendFromLink';
import { AccountDataCard } from '../components/AccountDataCard';
import { TwoStepCard } from '../components/TwoStepCard';
import { FamilyCard } from '../components/FamilyCard';
import { PushCard } from '../components/PushCard';
import { CalendarCard } from '../components/CalendarCard';
import { TelegramCard } from '../components/TelegramCard';
import { useBookText } from '../utils/bookText';
import { coverOfSize } from '../utils/covers';
import type { Order } from '../types';
import { BorrowingHistory } from '../components/BorrowingHistory';
import { Link } from 'react-router';

const MIN_PASSWORD_LENGTH = 8;

function ContactRow({ label, value, isPreferred }: { label: string; value?: string; isPreferred?: boolean }) {
  if (!value) return null;
  return (
    <div className="flex items-center gap-3">
      <div className="p-2 bg-primary/10 rounded-lg"><MessageCircle className="w-5 h-5 text-primary" /></div>
      <div className="flex-1">
        <div className="flex items-center gap-1.5">
          <p className="text-sm text-muted-foreground">{label}</p>
          {isPreferred && <Star className="w-3 h-3 fill-amber-400 text-amber-400" />}
        </div>
        <p>{value}</p>
      </div>
    </div>
  );
}

const CONTACT_FIELDS: { key: PreferredContact; labelKey: string; placeholder: string; type: string }[] = [
  { key: 'whatsapp',  labelKey: 'auth.whatsapp',  placeholder: '+1 234 567 8900', type: 'text' },
  { key: 'telegram',  labelKey: 'auth.telegram',  placeholder: '@username',       type: 'text' },
  { key: 'instagram', labelKey: 'auth.instagram', placeholder: '@handle',         type: 'text' },
  { key: 'phone',     labelKey: 'auth.phone',     placeholder: '+1 234 567 8900', type: 'tel'  },
];

export default function Profile() {
  const { t } = useTranslation();
  const textOf = useBookText();
  const { user, updateUser, changePassword } = useAuth();
  const { getOrdersForUser, cancelOrder, renewOrder } = useOrders();
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [renewingId, setRenewingId] = useState<string | null>(null);
  const rules = useLibraryRules();
  const { entries: waitlist } = useWaitlist();
  const fmt = useFormat();
  const { confirm, confirmDialog } = useConfirm();
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isPasswordDialogOpen, setIsPasswordDialogOpen] = useState(false);

  const [editName, setEditName] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editWhatsapp, setEditWhatsapp] = useState('');
  const [editTelegram, setEditTelegram] = useState('');
  const [editInstagram, setEditInstagram] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [editPreferred, setEditPreferred] = useState<PreferredContact | ''>('');

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [passwordError, setPasswordError] = useState('');

  if (!user) return null;

  const userOrders = getOrdersForUser(user.id);
  const pendingOrders = userOrders.filter(o => o.status === 'pending');

  const handleCancelRequest = async (orderId: string) => {
    setCancellingId(orderId);
    const result = await cancelOrder(orderId);
    setCancellingId(null);
    if (result.ok) toast.success(t('profile.requestCancelled'));
    else toast.error(errorMessage(t, result.error));
  };
  const borrowedOrders = userOrders.filter(o => o.status === 'confirmed');
  const borrowedCount = borrowedOrders.reduce((sum, o) => sum + o.books.length, 0);
  const borrowedBooks = borrowedOrders.flatMap(o => o.books.map(book => ({
    bookId: book.id,
    book,
    borrowedDate: o.confirmedAt || o.orderedAt,
    returnDate: o.dueDate,
  })));

  // The server has the final say; this only decides whether to offer the button.
  const canRenew = (order: Order) =>
    rules !== null && (order.renewalCount ?? 0) < rules.maxRenewals && daysUntil(order.dueDate) >= 0;

  const handleRenew = async (order: Order) => {
    setRenewingId(order.id);
    const result = await renewOrder(order.id);
    setRenewingId(null);
    if (result.ok) toast.success(t('profile.loanExtended', { date: fmt.date(result.data.dueDate) }));
    else toast.error(errorMessage(t, result.error));
  };

  const isOverdue = (returnDate: string) => daysUntil(returnDate) < 0;

  const getDaysUntilReturn = (returnDate: string) => daysUntil(returnDate);

  const handleEditClick = () => {
    setEditName(user.name);
    setEditEmail(user.email);
    setEditWhatsapp(user.contacts?.whatsapp ?? '');
    setEditTelegram(user.contacts?.telegram ?? '');
    setEditInstagram(user.contacts?.instagram ?? '');
    setEditPhone(user.contacts?.phone ?? '');
    setEditPreferred(user.contacts?.preferred ?? '');
    setError('');
    setIsEditDialogOpen(true);
  };

  const handleSaveProfile = async () => {
    setError('');
    if (!editName.trim()) { setError(t('profile.nameEmpty')); return; }
    if (!editEmail.trim()) { setError(t('profile.emailEmpty')); return; }

    const contacts: UserContacts = {
      whatsapp: editWhatsapp.trim() || undefined,
      telegram: editTelegram.trim() || undefined,
      instagram: editInstagram.trim() || undefined,
      phone: editPhone.trim() || undefined,
      preferred: editPreferred || undefined,
    };

    if (!contacts.whatsapp && !contacts.telegram && !contacts.instagram && !contacts.phone) {
      setError(t('auth.contactRequired'));
      return;
    }

    const result = await updateUser(editName, editEmail, contacts);
    if (result.ok) {
      setIsEditDialogOpen(false);
      toast.success(t('profile.profileUpdated'));
    } else {
      setError(
        result.error.code === 'EMAIL_ALREADY_EXISTS'
          ? t('profile.emailTaken')
          : errorMessage(t, result.error),
      );
    }
  };

  const handleOpenPasswordDialog = () => {
    setCurrentPassword(''); setNewPassword(''); setConfirmPassword(''); setPasswordError('');
    setIsPasswordDialogOpen(true);
  };

  const handleChangePassword = async () => {
    setPasswordError('');
    if (!currentPassword) { setPasswordError(t('profile.enterCurrentPasswordError')); return; }
    if (newPassword.length < MIN_PASSWORD_LENGTH) { setPasswordError(t('profile.passwordLengthError')); return; }
    if (newPassword !== confirmPassword) { setPasswordError(t('profile.passwordsNoMatch')); return; }

    const result = await changePassword(currentPassword, newPassword);
    if (result.ok) {
      setIsPasswordDialogOpen(false);
      toast.success(t('profile.passwordChanged'));
    } else {
      setPasswordError(errorMessage(t, result.error));
    }
  };

  const contacts = user.contacts;
  const hasContacts = contacts && (contacts.whatsapp || contacts.telegram || contacts.instagram || contacts.phone);

  return (
    <div className="container mx-auto px-4 py-6 space-y-6">
      <h1>{t('profile.title')}</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>{t('profile.personalInfo')}</CardTitle>
              <CardDescription>{t('profile.personalInfoDesc')}</CardDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={handleEditClick} aria-label={t('profile.editProfile')}>
              <Pencil className="w-4 h-4" />
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg"><UserIcon className="w-5 h-5 text-primary" /></div>
              <div>
                <p className="text-sm text-muted-foreground">{t('profile.name')}</p>
                <p>{user.name}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg"><Mail className="w-5 h-5 text-primary" /></div>
              <div>
                <p className="text-sm text-muted-foreground">{t('profile.email')}</p>
                <p>{user.email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg"><BookOpen className="w-5 h-5 text-primary" /></div>
              <div>
                <p className="text-sm text-muted-foreground">{t('profile.role')}</p>
                <Badge variant="outline" className="capitalize">{t(`admin.roles.${user.role}`)}</Badge>
              </div>
            </div>

            {hasContacts && (
              <div className="border-t border-border pt-3 space-y-3">
                <p className="text-sm font-medium">{t('auth.contactInfo')}</p>
                <ContactRow label={t('auth.whatsapp')} value={contacts?.whatsapp} isPreferred={contacts?.preferred === 'whatsapp'} />
                <ContactRow label={t('auth.telegram')} value={contacts?.telegram} isPreferred={contacts?.preferred === 'telegram'} />
                <ContactRow label={t('auth.instagram')} value={contacts?.instagram} isPreferred={contacts?.preferred === 'instagram'} />
                <ContactRow label={t('auth.phone')} value={contacts?.phone} isPreferred={contacts?.preferred === 'phone'} />
              </div>
            )}

            <Button variant="outline" className="w-full mt-2" onClick={handleOpenPasswordDialog}>
              {t('profile.changePassword')}
            </Button>
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>{t('profile.borrowingStats')}</CardTitle>
            <CardDescription>{t('profile.borrowingStatsDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-3xl mb-1">{borrowedBooks.length}</p>
                <p className="text-sm text-muted-foreground">{t('profile.currentlyBorrowed')}</p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-3xl mb-1">{borrowedBooks.filter(b => !isOverdue(b.returnDate)).length}</p>
                <p className="text-sm text-muted-foreground">{t('profile.onTime')}</p>
              </div>
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-3xl mb-1">{borrowedBooks.filter(b => isOverdue(b.returnDate)).length}</p>
                <p className="text-sm text-muted-foreground">{t('profile.overdue')}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <LateReturnsCard orders={userOrders} />
      <ExtendFromLink orders={userOrders} confirm={confirm} renew={handleRenew} />
      <HeldForYouCard />
      <ReservationsCard />
      <NextInSeriesCard />

      <ReadingListCard />
      <FamilyCard />
      <ReadingLogCard />
      <Card>
        <CardHeader>
          <CardTitle>{t('suggest.profileTitle')}</CardTitle>
          <CardDescription>{t('suggest.profileText')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" asChild>
            <Link to="/suggestions">{t('suggest.open')}</Link>
          </Button>
        </CardContent>
      </Card>

      {waitlist.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('waitlist.title')}</CardTitle>
            <CardDescription>{t('waitlist.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {waitlist.map(({ book, createdAt }) => {
              const text = textOf(book);
              return (
              <div key={book.id} className="flex items-center gap-4 p-3 border border-border rounded-lg">
                <div className="w-10 h-14 flex-shrink-0 overflow-hidden rounded bg-muted">
                  <img src={coverOfSize(book.coverImage, 'S')} alt="" className="w-full h-full object-cover" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="truncate">{text.title}</h3>
                  <p className="text-sm text-muted-foreground truncate">
                    {text.author} · {t('waitlist.since', { date: fmt.date(createdAt) })}
                  </p>
                </div>
                <WaitlistButton bookId={book.id} groupId={book.groupId} title={text.title} />
              </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {pendingOrders.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('profile.pendingRequests')}</CardTitle>
            <CardDescription>{t('profile.pendingRequestsDesc')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {pendingOrders.map(order => (
              <div key={order.id} className="p-4 border border-border rounded-lg space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Clock className="w-4 h-4" />
                    <span className="font-medium text-foreground">{orderLabel(order)}</span>
                    <span>{t('profile.requestedOn')}: {fmt.date(order.orderedAt)}</span>
                    <Badge variant="outline">{order.books.length} {t('cart.books')}</Badge>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={cancellingId === order.id}
                    onClick={async () => {
                      const confirmed = await confirm({
                        title: t('confirm.cancelRequestTitle'),
                        description: t('confirm.cancelRequestDesc'),
                        confirmLabel: t('confirm.cancelRequest'),
                        cancelLabel: t('confirm.keepRequest'),
                        destructive: true,
                      });
                      if (confirmed) handleCancelRequest(order.id);
                    }}
                  >
                    {t('profile.cancelRequest')}
                  </Button>
                </div>
                {order.childName && <p className="text-sm text-muted-foreground">{t('family.forChild', { name: order.childName })}</p>}
                <PickupLine order={order} />
                <div className="flex gap-2 flex-wrap">
                  {order.books.map(book => (
                    <div key={book.id} className="w-10 h-14 overflow-hidden rounded bg-muted" title={book.title}>
                      <img src={coverOfSize(book.coverImage, 'S')} alt={book.title} className="w-full h-full object-cover" />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t('profile.currentlyBorrowedBooks')}</CardTitle>
          <CardDescription>{t('profile.booksToReturn')}</CardDescription>
        </CardHeader>
        <CardContent>
          {borrowedCount === 0 ? (
            <div className="text-center py-8 text-muted-foreground">{t('profile.noBorrowedBooks')}</div>
          ) : (
            <div className="space-y-6">
              {borrowedOrders.map((order) => {
                const daysLeft = getDaysUntilReturn(order.dueDate);
                const overdue = isOverdue(order.dueDate);
                const renewalsLeft = rules ? Math.max(rules.maxRenewals - (order.renewalCount ?? 0), 0) : 0;
                return (
                  <section key={order.id} aria-label={orderLabel(order)} className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="font-medium">{orderLabel(order)}</span>
                        <span className="text-muted-foreground">{t('profile.returnBy')}: {fmt.date(order.dueDate)}</span>
                        {overdue ? (
                          <Badge variant="destructive">{t('profile.overdueBy')} {Math.abs(daysLeft)} {t('myBooks.days')}</Badge>
                        ) : daysLeft <= 3 ? (
                          <Badge className="bg-amber-700 text-white">{t('profile.dueIn')} {daysLeft} {t('myBooks.days')}</Badge>
                        ) : (
                          <Badge className="bg-green-700 text-white">{daysLeft} {t('profile.daysLeft')}</Badge>
                        )}
                      </div>
                      {canRenew(order) ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={renewingId === order.id}
                          onClick={() => handleRenew(order)}
                          title={t('profile.renewalsLeft', { count: renewalsLeft })}
                        >
                          <CalendarPlus className="w-4 h-4 mr-2" aria-hidden="true" />
                          {t('profile.extendLoan', { count: rules?.loanPeriodDays ?? 0 })}
                        </Button>
                      ) : (order.renewalCount ?? 0) > 0 ? (
                        <span className="text-xs text-muted-foreground">{t('profile.loanAlreadyExtended')}</span>
                      ) : null}
                    </div>
                    {order.books.map((book) => (
                      <div key={book.id} className="flex gap-4 p-4 border border-border rounded-lg hover:bg-muted/50 transition-colors">
                        <div className="w-16 h-24 flex-shrink-0 overflow-hidden rounded bg-muted">
                          <img src={coverOfSize(book.coverImage, 'S')} alt={book.title} className="w-full h-full object-cover" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="truncate mb-1">{book.title}</h3>
                          <p className="text-sm text-muted-foreground mb-2">{book.author}</p>
                          <div className="flex items-center gap-1 text-sm text-muted-foreground">
                            <Calendar className="w-4 h-4" />
                            <span>{t('profile.borrowed')}: {fmt.date(order.confirmedAt || order.orderedAt)}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </section>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <BorrowingHistory orders={userOrders} />

      {/* Edit Profile Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('profile.editProfile')}</DialogTitle>
            <DialogDescription>{t('profile.editProfileDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="edit-name">{t('profile.fullName')}</Label>
              <Input id="edit-name" value={editName} onChange={e => setEditName(e.target.value)} placeholder={t('profile.yourName')} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-email">{t('profile.email')}</Label>
              <Input id="edit-email" type="email" value={editEmail} onChange={e => setEditEmail(e.target.value)} placeholder={t('profile.yourEmail')} />
            </div>
            <div className="space-y-3 pt-1">
              <div>
                <p className="text-sm font-medium">{t('auth.contactInfo')} <span className="text-muted-foreground font-normal text-xs">({t('auth.atLeastOne')})</span></p>
                <p className="text-xs text-muted-foreground mt-0.5">{t('auth.starToMarkPreferred')}</p>
              </div>
              {(() => {
                const vals: Record<PreferredContact, string> = { whatsapp: editWhatsapp, telegram: editTelegram, instagram: editInstagram, phone: editPhone };
                const setters: Record<PreferredContact, (v: string) => void> = { whatsapp: setEditWhatsapp, telegram: setEditTelegram, instagram: setEditInstagram, phone: setEditPhone };
                return CONTACT_FIELDS.map(({ key, labelKey, placeholder, type }) => (
                  <div key={key} className="space-y-1.5">
                    <Label htmlFor={`edit-${key}`}>{t(labelKey)}</Label>
                    <div className="flex gap-2">
                      <Input
                        id={`edit-${key}`}
                        type={type}
                        value={vals[key]}
                        onChange={e => { setters[key](e.target.value); if (!e.target.value.trim() && editPreferred === key) setEditPreferred(''); }}
                        placeholder={placeholder}
                        className="flex-1"
                      />
                      <button
                        type="button"
                        title={t('auth.markPreferred')}
                        aria-label={t('a11y.markPreferred', { method: t(labelKey) })}
                        aria-pressed={editPreferred === key}
                        disabled={!vals[key].trim()}
                        onClick={() => setEditPreferred(prev => prev === key ? '' : key)}
                        className={`px-2 rounded-md border transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
                          editPreferred === key
                            ? 'bg-amber-400 border-amber-500 text-white'
                            : 'border-border text-muted-foreground hover:border-amber-400 hover:text-amber-500'
                        }`}
                      >
                        <Star className="w-4 h-4" fill={editPreferred === key ? 'currentColor' : 'none'} />
                      </button>
                    </div>
                  </div>
                ));
              })()}
            </div>
            {error && <div role="alert" className="text-sm text-destructive dark:text-red-300 bg-destructive/10 p-3 rounded-md">{error}</div>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>{t('admin.cancel')}</Button>
            <Button onClick={handleSaveProfile}>{t('admin.saveChanges')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change Password Dialog */}
      <Dialog open={isPasswordDialogOpen} onOpenChange={setIsPasswordDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('profile.changePasswordTitle')}</DialogTitle>
            <DialogDescription>{t('profile.changePasswordDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="current-password">{t('profile.currentPassword')}</Label>
              <Input id="current-password" type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder={t('profile.enterCurrentPassword')} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">{t('profile.newPassword')}</Label>
              <Input id="new-password" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder={t('profile.newPasswordPlaceholder')} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">{t('profile.confirmPassword')}</Label>
              <Input id="confirm-password" type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder={t('profile.repeatPassword')} />
            </div>
            {passwordError && <div role="alert" className="text-sm text-destructive dark:text-red-300 bg-destructive/10 p-3 rounded-md">{passwordError}</div>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsPasswordDialogOpen(false)}>{t('admin.cancel')}</Button>
            <Button onClick={handleChangePassword}>{t('profile.changePassword')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <TelegramCard />
      <CalendarCard />
      <PushCard />
      <TwoStepCard />
      <AccountDataCard />
      {confirmDialog}
    </div>
  );
}
