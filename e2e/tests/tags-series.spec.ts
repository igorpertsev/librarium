import { expect, test } from '@playwright/test';
import { createBook, registerCustomer, unique } from '../helpers';

test('a reader filters by tags, opens a series in volume order and takes all of it', async ({ page, request }) => {
  const id = unique();
  const series = `Saga ${id}`;
  // Created out of order: the series view sorts by volume number, not by title or date.
  await createBook(request, { title: `Saga ${id} two`, tags: ['fantasy'], series_name: series, series_position: 2 });
  await createBook(request, {
    title: `Saga ${id} one`,
    tags: ['fantasy', 'adventure'],
    series_name: series,
    series_position: 1,
  });
  await createBook(request, { title: `Saga ${id} three`, series_name: series, series_position: 3 });
  await createBook(request, { title: `Lone ${id}`, tags: ['adventure', 'fantasy'] });
  await createBook(request, { title: `Other ${id}`, tags: ['adventure'] });

  await registerCustomer(page);
  await page.goto(`/?q=${id}&sort=title`);
  const titles = page.locator('[data-slot=card] h2');
  await expect(titles).toHaveCount(5);

  // Both tags: only the books that have each of them.
  await page.getByRole('combobox', { name: 'Tags' }).click();
  await page.getByRole('option', { name: /^Fantasy/ }).click();
  await page.getByRole('option', { name: /^Adventure/ }).click();
  await page.keyboard.press('Escape');
  await expect(page).toHaveURL(/tags=fantasy%2Cadventure|tags=fantasy,adventure/);
  await expect(titles).toHaveText([`Lone ${id}`, `Saga ${id} one`], { useInnerText: true });

  // A removed chip widens the filter again.
  await page.getByRole('button', { name: 'Remove tag Adventure' }).click();
  await expect(titles).toHaveCount(3);

  // The series link on a card shows the whole series, volume 1 first.
  const card = page.locator('[data-slot=card]').filter({ hasText: `Saga ${id} two` });
  await card.getByRole('link', { name: `Show the series: ${series}, book 2` }).click();
  await expect(page.getByRole('heading', { name: series, exact: true })).toBeVisible();
  await expect(page.getByText('3 titles in the library')).toBeVisible();
  await expect(titles).toHaveText([`Saga ${id} one`, `Saga ${id} two`, `Saga ${id} three`]);

  await page.getByRole('button', { name: 'Take the whole series' }).click();
  await expect(page.getByText('3 books of the series added to the cart')).toBeVisible();
  await page.goto('/cart');
  for (const volume of ['one', 'two', 'three']) {
    await expect(page.getByText(`Saga ${id} ${volume}`).first()).toBeVisible();
  }
});
