import { useCallback, useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { Bell, BookOpenCheck, CalendarClock, CircleAlert, Clock, PackageCheck, PackageX, Sparkles, Inbox as InboxIcon, type LucideIcon } from 'lucide-react';
import { usersApi } from '../../api/endpoints';
import { bookFromDto } from '../../api/mappers';
import type { InboxDto, InboxItemDto } from '../../api/types';
import { useAuth } from '../contexts/AuthContext';
import { useCatalog } from '../contexts/CatalogContext';
import { useBookText } from '../utils/bookText';
import { useFormat } from '../utils/format';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { cn } from './ui/utils';

const POLL_MS = 60_000;

const ICONS: Record<InboxItemDto['kind'], LucideIcon> = {
  order_received: InboxIcon,
  order_confirmed: PackageCheck,
  order_cancelled: PackageX,
  due_soon: Clock,
  overdue: CircleAlert,
  book_available: Sparkles,
  book_held: BookOpenCheck,
  reservation_ready: CalendarClock,
};

/** Header bell: the reader's latest news (the same events as the emails). */
export function NotificationBell({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { version } = useCatalog();
  const navigate = useNavigate();
  const fmt = useFormat();
  const textOf = useBookText();
  const [inbox, setInbox] = useState<InboxDto | null>(null);
  const [open, setOpen] = useState(false);
  const titleId = useId();

  const load = useCallback(() => {
    usersApi.notifications().then(setInbox, () => undefined);
  }, []);

  useEffect(() => {
    if (!user) {
      setInbox(null);
      return;
    }
    load();
    const refresh = () => document.visibilityState === 'visible' && load();
    const timer = window.setInterval(refresh, POLL_MS);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [user, load, version]);

  if (!user) return null;
  const unread = inbox?.unread ?? 0;

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (next && unread > 0) {
      // Seen once the list is open; the items keep their unread look until it closes.
      usersApi.markNotificationsRead().then(
        () => setInbox((current) => (current ? { ...current, unread: 0 } : current)),
        () => undefined,
      );
    }
    if (!next) load();
  };

  const message = (item: InboxItemDto) => {
    const title = item.book ? textOf(bookFromDto(item.book)).title : '';
    return t(`inbox.kinds.${item.kind}`, { number: item.order_number ?? '', title });
  };

  const openItem = (item: InboxItemDto) => {
    setOpen(false);
    if (item.kind === 'book_available' && item.book) navigate(`/books/${item.book.id}`);
    else navigate('/profile');
  };

  const label = unread > 0 ? t('inbox.labelUnread', { count: unread }) : t('inbox.label');
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger
        aria-label={label}
        title={label}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-md hover:bg-accent hover:text-accent-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        data-testid="notification-bell"
      >
        <Bell className={compact ? 'w-5 h-5' : 'w-4 h-4'} aria-hidden="true" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[1.1rem] h-[1.1rem] rounded-full bg-primary px-1 text-[10px] leading-[1.1rem] text-primary-foreground text-center">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 max-w-[calc(100vw-2rem)] p-0" aria-labelledby={titleId}>
        <p id={titleId} className="px-4 py-3 text-sm font-medium border-b border-border">{t('inbox.title')}</p>
        {!inbox || inbox.items.length === 0 ? (
          <p className="px-4 py-6 text-sm text-muted-foreground text-center">{t('inbox.empty')}</p>
        ) : (
          <ul className="max-h-96 overflow-y-auto divide-y divide-border">
            {inbox.items.map((item) => {
              const Icon = ICONS[item.kind];
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => openItem(item)}
                    className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
                  >
                    <Icon className="w-4 h-4 mt-0.5 shrink-0 text-primary" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className={cn('block text-sm', !item.read && 'font-medium')}>{message(item)}</span>
                      <span className="block text-xs text-muted-foreground">{fmt.dateTime(item.created_at)}</span>
                    </span>
                    {!item.read && (
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary">
                        <span className="sr-only">{t('inbox.new')}</span>
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
