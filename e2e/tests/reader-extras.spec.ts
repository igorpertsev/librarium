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
