import { expect, test } from '@playwright/test';
import { ADMIN, createBook, registerCustomer, signIn, signOut, unique } from '../helpers';

test('readers suggest a book, vote for it, and hear when the library adds it', async ({ page, request }) => {
  const title = `Wish ${unique()}`;
  const author = 'Wanted Writer';

  // A search that finds nothing offers to suggest the book.
  const first = await registerCustomer(page);
  await page.goto(`/?q=${encodeURIComponent(title)}`);
  await page.getByRole('button', { name: 'Not here? Suggest it to the library' }).click();
  await expect(page).toHaveURL(/\/suggestions\?title=/);
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue(title);
  await page.getByLabel('Author', { exact: true }).fill(author);
  await page.getByRole('button', { name: 'Suggest', exact: true }).click();
  await expect(page.getByText('Thank you! Your suggestion was added.')).toBeVisible();
  const item = page.getByRole('listitem').filter({ hasText: title });
  await expect(item.getByRole('button', { name: `Take back your vote for “${title}”` })).toHaveText('1');

  // Another reader suggests the same book: it becomes a vote.
  await signOut(page);
  await registerCustomer(page);
  await page.goto('/suggestions');
  await page.getByLabel('Title', { exact: true }).fill(title.toUpperCase());
  await page.getByLabel('Author', { exact: true }).fill(author);
  await page.getByRole('button', { name: 'Suggest', exact: true }).click();
  await expect(page.getByText('Someone suggested this book already; your vote was added.')).toBeVisible();
  await expect(item.getByRole('button', { name: `Take back your vote for “${title}”` })).toHaveText('2');

  // The library buys it; the first reader finds the news under the bell.
  await createBook(request, { title, author });
  await signOut(page);
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: 'Suggestions' }).click();
  await page.getByRole('combobox', { name: `Status of “${title}”` }).selectOption('added');
  await expect(page.getByText(`“${title}” marked as added; voters will be emailed`)).toBeVisible();
  await signOut(page);
  await signIn(page, first);
  await page.getByRole('button', { name: /^Notifications: \d+ new$/ }).click();
  await expect(page.getByRole('dialog', { name: 'Notifications' })).toContainText(`“${title}”, which you asked for, is in the library`);
});
