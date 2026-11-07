import { useEffect, useState } from 'react';
import { libraryApi } from '../../api/endpoints';
import { toMoney } from '../../api/mappers';
import type { LibraryRulesDto } from '../../api/types';

export interface LibraryRules {
  booksPerBatch: number;
  loanPeriodDays: number;
  maxRenewals: number;
  /** How long a returned book is held for the next reader (0: no holds). */
  holdHours: number;
  /** Readers with overdue loans cannot place new orders. */
  blockOverdue: boolean;
  /** Fee per day for late returns (0: no fees). */
  lateFeePerDay: number;
  currency: string;
  /** IANA time zone of opening hours and pickup slots. */
  timezone: string;
  /** Username of the library's Telegram bot, when notifications can go there. */
  telegramBot: string | null;
  /** VAPID public key for notifications on this device (null: push is not set up). */
  webPushKey: string | null;
}

let cached: Promise<LibraryRules> | null = null;

function loadRules(): Promise<LibraryRules> {
  cached ??= libraryApi
    .rules()
    .then((dto: LibraryRulesDto) => ({
      booksPerBatch: dto.books_per_batch,
      loanPeriodDays: dto.loan_period_days,
      maxRenewals: dto.max_renewals,
      holdHours: dto.hold_hours,
      blockOverdue: dto.block_overdue,
      lateFeePerDay: toMoney(dto.late_fee_per_day),
      currency: dto.currency,
      timezone: dto.timezone,
      telegramBot: dto.telegram_bot ?? null,
      webPushKey: dto.web_push_key ?? null,
    }))
    .catch((error: unknown) => {
      cached = null; // try again next time
      throw error;
    });
  return cached;
}

/** Lending rules from GET /library/rules (null while loading or if they cannot be loaded). */
export function useLibraryRules(): LibraryRules | null {
  const [rules, setRules] = useState<LibraryRules | null>(null);
  useEffect(() => {
    let active = true;
    loadRules().then(
      (value) => active && setRules(value),
      () => undefined,
    );
    return () => {
      active = false;
    };
  }, []);
  return rules;
}

/** Forget cached rules after an administrator changed them. */
export function invalidateLibraryRules(): void {
  cached = null;
}
