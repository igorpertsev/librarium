/**
 * Aliases for the DTOs generated from the backend OpenAPI schema.
 * Regenerate `generated/schema.d.ts` with `pnpm api:types` (never edit it by hand).
 */
import type { components, paths } from './generated/schema';

type Schemas = components['schemas'];

export type BookDto = Schemas['BookRead'];
export type BookBriefDto = Schemas['BookBrief'];
export type BookPageDto = Schemas['BookPage'];
export type BookCreateDto = Schemas['BookCreate'];
export type BookUpdateDto = Schemas['BookUpdate'];
export type BookStatsDto = Schemas['BookStats'];
export type BookStatusDto = Schemas['BookStatus'];
export type CartDto = Schemas['CartRead'];
export type CartItemDto = Schemas['CartItemRead'];
export type OrderDto = Schemas['OrderRead'];
export type OrderItemDto = Schemas['OrderItemRead'];
export type OrderPageDto = Schemas['OrderPage'];
export type OrderStatusDto = Schemas['OrderStatus'];
export type UserDto = Schemas['UserRead'];
export type UserUpdateDto = Schemas['UserUpdate'];
export type AdminUserDto = Schemas['AdminUserRead'];
export type AdminUserPageDto = Schemas['AdminUserPage'];
export type AdminUserUpdateDto = Schemas['AdminUserUpdate'];
export type ActiveLoanDto = Schemas['ActiveLoan'];
export type RegisterDto = Schemas['RegisterRequest'];
export type LoginDto = Schemas['LoginRequest'];
export type ChangePasswordDto = Schemas['ChangePasswordRequest'];
export type ForgotPasswordDto = Schemas['ForgotPasswordRequest'];
export type ResetPasswordDto = Schemas['ResetPasswordRequest'];
export type TokenResponseDto = Schemas['TokenResponse'];
export type LibrarySettingsDto = Schemas['LibrarySettingsRead'];
export type LibraryRulesDto = Schemas['LibraryRules'];
export type PickupPointDto = Schemas['PickupPointRead'];
export type PickupPointCreateDto = Schemas['PickupPointCreate'];
export type PickupPointUpdateDto = Schemas['PickupPointUpdate'];
export type PickupSlotDto = Schemas['PickupSlot'];
export type PickupChoiceDto = Schemas['PickupChoice'];
export type OpeningHoursDto = Schemas['OpeningHours'];
export type WaitlistEntryDto = Schemas['WaitlistEntryRead'];
export type LibrarySettingsUpdateDto = Schemas['LibrarySettingsUpdate'];
export type ErrorResponseDto = Schemas['ErrorResponse'];
export type ReminderQueuedDto = Schemas['ReminderQueued'];
export type BookLookupDto = Schemas['BookLookup'];
export type BookImportResultDto = Schemas['BookImportResult'];
export type ReportSummaryDto = Schemas['ReportSummaryRead'];
export type TagBriefDto = Schemas['TagBrief'];
export type TagDto = Schemas['TagRead'];
export type TagCreateDto = Schemas['TagCreate'];
export type TagUpdateDto = Schemas['TagUpdate'];
export type SeriesBriefDto = Schemas['SeriesBrief'];
export type SeriesDto = Schemas['SeriesRead'];
export type SeriesCreateDto = Schemas['SeriesCreate'];
export type SeriesUpdateDto = Schemas['SeriesUpdate'];
export type LookupSeriesDto = Schemas['LookupSeries'];
export type BookTranslationDto = Schemas['BookTranslationRead'];
export type ReadingListItemDto = Schemas['ReadingListItemRead'];
export type SeriesNeighboursDto = Schemas['SeriesNeighbours'];
export type QualityIssueDto = Schemas['QualityIssue'];
export type QualitySummaryDto = Schemas['QualitySummary'];
export type DemandDto = Schemas['DemandRead'];
export type ReviewSummaryDto = Schemas['ReviewSummaryRead'];
export type HeldBookDto = Schemas['HeldBookRead'];
export type MyReviewDto = Schemas['MyReviewRead'];
export type ReviewDto = Schemas['ReviewRead'];
export type ReviewStatusDto = Schemas['ReviewStatus'];
export type ModerationReviewPageDto = Schemas['ModerationReviewPage'];
export type BookTranslationInDto = Schemas['BookTranslationIn'];
export type TranslationSuggestRequestDto = Schemas['TranslationSuggestRequest'];
export type TranslationSuggestionDto = Schemas['TranslationSuggestion'];

export type BookListQuery = NonNullable<paths['/api/v1/books']['get']['parameters']['query']>;
export type AdminBookListQuery = NonNullable<
  paths['/api/v1/admin/books']['get']['parameters']['query']
>;
export type OrderListQuery = NonNullable<paths['/api/v1/orders']['get']['parameters']['query']>;
export type AdminOrderListQuery = NonNullable<
  paths['/api/v1/admin/orders']['get']['parameters']['query']
>;
export type AdminUserListQuery = NonNullable<
  paths['/api/v1/admin/users']['get']['parameters']['query']
>;

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
