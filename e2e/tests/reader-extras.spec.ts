import { expect, test } from '@playwright/test';
import { createBook, registerCustomer, unique } from '../helpers';

test('a reader filters by language, saves a book, follows an author and a series', async ({ page, request }) => {
  const id = unique();
  const author = `Author ${id}`;
  const series = `Cycle ${id}`;
  await createBook(request, { title: `${id} one`, author, language: 'en', series_name: series, series_position: 1 });
  await createBook(request, { title: `${id} two`, author, language: 'en', series_name: series, series_position: 2 });
  await createBook(request, { title: `${id} русская`, author: `Автор ${id}`, language: 'ru' });

  await registerCustomer(page);
  const titles = page.locator('[data-slot=card] h2');

  // Language filter: only the Russian book.
  await page.goto(`/?q=${id}&sort=title`);
  await expect(titles).toHaveCount(3);
  await page.getByRole('combobox', { name: 'Language' }).click();
  await page.getByRole('option', { name: 'Russian' }).click();
  await expect(page).toHaveURL(/language=ru/);
  await expect(titles).toHaveText([`${id} русская`]);

  // Author page from a card.
  await page.goto(`/?q=${id}&sort=title`);
  await page.getByRole('link', { name: `All books by ${author}` }).first().click();
  await expect(page.getByRole('heading', { name: author, exact: true })).toBeVisible();
  await expect(titles).toHaveCount(2);

  // Series: the dialog of volume 1 offers volume 2.
  await page.getByRole('button', { name: `${id} one`, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: `Next: ${id} two` }).click();
  await expect(dialog.getByRole('heading', { name: `${id} two` })).toBeVisible();

  // Want to read: saved from the dialog, listed on the profile, removed there.
  await dialog.getByRole('button', { name: 'Want to read' }).click();
  await expect(page.getByText(`“${id} two” saved to Want to read`)).toBeVisible();
  await page.keyboard.press('Escape');
  await page.goto('/profile');
  const saved = page.locator('h3', { hasText: `${id} two` });
  await expect(saved).toBeVisible();
  await page.getByRole('button', { name: `Remove “${id} two” from Want to read` }).click();
  await expect(saved).toHaveCount(0);
});

test('a reader reserves a book for a date and cancels the reservation', async ({ page, request }) => {
  const title = `Holiday ${unique()}`;
  await createBook(request, { title });
  await registerCustomer(page);
  await page.goto(`/?q=${encodeURIComponent(title)}`);
  await page.getByRole('button', { name: title, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Reserve for a date' }).click();
  const day = new Date();
  day.setDate(day.getDate() + 14);
  const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
  await dialog.getByLabel('I want it from').fill(iso);
  await dialog.getByRole('button', { name: 'Reserve', exact: true }).click();
  await expect(dialog.getByText('Reserved for you from')).toBeVisible();
  // Kept for the reader: nobody else can borrow it any more.
  await expect(dialog.getByRole('button', { name: 'Not Available' })).toBeDisabled();
  await page.keyboard.press('Escape');

  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: 'Reserved for later' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel reservation' }).click();
  await expect(page.getByText(`Reservation of “${title}” cancelled`)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Reserved for later' })).toHaveCount(0);
});

test('a reader logs a finished book and earns the first badge', async ({ page, request }) => {
  const title = `Finished ${unique()}`;
  await createBook(request, { title });
  await registerCustomer(page);
  await page.goto(`/?q=${encodeURIComponent(title)}`);
  await page.getByRole('button', { name: title, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: "I've read it" }).click();
  await expect(page.getByText(`“${title}” added to your reading log`)).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Read', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');

  await page.goto('/profile');
  const log = page.getByTestId('reading-log');
  await expect(log).toContainText('1 this year · 1 in total · 1 badge');
  await expect(log.getByRole('listitem').filter({ hasText: 'First book' })).toContainText('Earned!');
  await expect(log).toContainText(title);
});
