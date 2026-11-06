import { expect, test } from '@playwright/test';
import { API_URL, createBook, registerCustomer, signOut, unique } from '../helpers';

test('visitors browse without an account, open a shared book and sign in to borrow', async ({ page, request }) => {
  const id = unique();
  const title = `Open ${id}`;
  await createBook(request, { title, description: 'For everyone to see.' });
  const found = await (await request.get(`${API_URL}/books`, { params: { q: id } })).json();
  const bookId: string = found.items[0].id;
  const customer = await registerCustomer(page);
  await signOut(page);

  // The catalogue is open: no sign-in page, and borrowing asks to sign in.
  await page.goto(`/?q=${id}`);
  const card = page.locator('[data-slot=card]').filter({ hasText: title });
  await expect(card.getByRole('heading', { name: title })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();

  // A shared link opens the book.
  await page.goto(`/books/${bookId}`);
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: title })).toBeVisible();
  await expect(page).toHaveTitle(`${title} — Little Dragon`);

  // Signing in from the book comes back to it, now with the cart button.
  await dialog.getByRole('button', { name: 'Sign in to borrow' }).click();
  await expect(page).toHaveURL('/login');
  await page.getByLabel('Email').fill(customer.email);
  await page.getByLabel('Password', { exact: true }).fill(customer.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(`/books/${bookId}`);
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Add to Cart' })).toBeVisible();
});
