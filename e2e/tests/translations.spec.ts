import { expect, test } from '@playwright/test';
import { createBook, registerCustomer, unique } from '../helpers';

test('a Russian reader sees and finds an English book by its Russian title', async ({ page, request }) => {
  const id = unique();
  await createBook(request, {
    title: `The Catcher ${id}`,
    author: 'J. D. Salinger',
    description: 'Holden wanders New York.',
    language: 'en',
    translations: [
      {
        language: 'ru',
        title: `Над пропастью ${id}`,
        author: 'Джером Сэлинджер',
        description: 'Холден бродит по Нью-Йорку.',
      },
    ],
  });

  await registerCustomer(page);
  await page.getByRole('button', { name: 'Settings' }).click();
  await page.getByRole('dialog').getByRole('combobox', { name: 'Language' }).click();
  await page.getByRole('option', { name: 'Russian' }).click();
  await page.keyboard.press('Escape');

  // Search by the Russian title finds the English book; the card shows both titles.
  await page.goto(`/?q=${encodeURIComponent(`над пропастью ${id}`)}`);
  const card = page.locator('[data-slot=card]').filter({ hasText: `Над пропастью ${id}` });
  await expect(card.getByRole('heading', { name: `Над пропастью ${id}` })).toBeVisible();
  await expect(card).toContainText(`The Catcher ${id}`);
  await expect(card).toContainText('Джером Сэлинджер');
  await expect(card).toContainText('Язык: английский');

  // The dialog shows the translated description and can show the original.
  await card.getByRole('button', { name: `Над пропастью ${id}`, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Холден бродит по Нью-Йорку.');
  await dialog.getByRole('button', { name: 'Показать оригинал' }).click();
  await expect(dialog).toContainText('Holden wanders New York.');
});
