import { expect, test, type Page } from '@playwright/test';
import { confirmOrder, createBooks, registerCustomer, setBatchSize, unique } from '../helpers';

test.beforeAll(async ({ request }) => {
  await setBatchSize(request, 1);
});
test.afterAll(async ({ request }) => {
  await setBatchSize(request, 5);
});

const bookCard = (page: Page, title: string) =>
  page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: title, exact: true }) });

/** Puts the book in the cart and checks out; returns the order id. */
async function borrow(page: Page, title: string): Promise<string> {
  await page.goto('/');
  await page.getByPlaceholder('Search books...').fill(title);
  await bookCard(page, title).getByRole('button', { name: 'Add to Cart' }).click();
  await page.getByRole('button', { name: /^Cart/ }).click();
  await page.getByRole('button', { name: 'Proceed to Checkout' }).click();
  const [placed] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/orders') && r.request().method() === 'POST'),
    page.getByRole('dialog').getByRole('button', { name: 'Place Order' }).click(),
  ]);
  expect(placed.status()).toBe(201);
  return (await placed.json()).id as string;
}

test('a reader extends a loan once', async ({ page, request }) => {
  const [title] = await createBooks(request, `Renew ${unique()}`, 1);
  await registerCustomer(page);
  await confirmOrder(request, await borrow(page, title));

  await page.goto('/profile');
  await page.getByRole('button', { name: /^Extend by 30 days/ }).click();
  await expect(page.getByText(/Loan extended/)).toBeVisible();
  await expect(page.getByText('Already extended')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Extend by/ })).toHaveCount(0);
});

test('a reader waits for a book that is out and can stop waiting', async ({ page, request, browser }) => {
  const [title] = await createBooks(request, `Waitlist ${unique()}`, 1);
  // Another reader borrows it.
  const other = await (await browser.newContext()).newPage();
  await registerCustomer(other);
  await borrow(other, title);

  await registerCustomer(page);
  await page.getByPlaceholder('Search books...').fill(title);
  const card = bookCard(page, title);
  await card.getByRole('button', { name: `Email me when “${title}” is available` }).click();
  await expect(card.getByRole('button', { name: `Stop waiting for “${title}”` })).toHaveAttribute('aria-pressed', 'true');

  await page.goto('/profile');
  const list = page.locator('[data-slot=card]').filter({ hasText: 'Waiting List' });
  await expect(list).toContainText(title);
  await list.getByRole('button', { name: `Stop waiting for “${title}”` }).click();
  await expect(page.locator('[data-slot=card]').filter({ hasText: 'Waiting List' })).toHaveCount(0);
});
