import { expect, test, type Page } from '@playwright/test';
import { ADMIN, createBooks, registerCustomer, setBatchSize, signIn, signOut, unique } from '../helpers';

test.beforeAll(async ({ request }) => {
  await setBatchSize(request, 2);
});
test.afterAll(async ({ request }) => {
  await setBatchSize(request, 5);
});

const bookCard = (page: Page, title: string) =>
  page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: title, exact: true }) });

test('a reader borrows a batch; the library hands it over and takes it back', async ({ page, request }) => {
  const titles = await createBooks(request, `Borrow ${unique()}`, 2);
  const customer = await registerCustomer(page);

  // Fill one batch from the catalogue.
  await page.getByPlaceholder('Search books...').fill(titles[0].replace(/ 1$/, ''));
  for (const title of titles) {
    const card = bookCard(page, title);
    await card.getByRole('button', { name: 'Add to Cart' }).click();
    await expect(card.getByRole('button', { name: 'Pending' })).toBeVisible();
  }
  await expect(page.getByText('1 batch ready')).toBeVisible();

  // Check out.
  await page.getByRole('button', { name: /^Cart/ }).click();
  await page.getByRole('button', { name: 'Proceed to Checkout' }).click();
  const [placed] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/orders') && r.request().method() === 'POST'),
    page.getByRole('dialog').getByRole('button', { name: 'Place Order' }).click(),
  ]);
  expect(placed.status()).toBe(201);
  const orderNumber = `#${(await placed.json()).number}`;
  await expect(page.getByText('Order Placed!')).toBeVisible();

  // The bell has the news; opening it marks it read.
  const bell = page.getByRole('button', { name: 'Notifications: 1 new' });
  await bell.click();
  await expect(page.getByRole('dialog', { name: 'Notifications' })).toContainText(`We received your request ${orderNumber}`);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Notifications', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'My Books' }).click();
  await expect(page.getByText(orderNumber)).toBeVisible();

  // The librarian confirms the order.
  await signOut(page);
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: /Orders/ }).click();
  await page.getByRole('searchbox').fill(orderNumber);
  const row = page.getByRole('row').filter({ hasText: orderNumber });
  await expect(row).toContainText(customer.name);
  await row.getByRole('button', { name: 'Confirm' }).click();
  await expect(row).toContainText('Confirmed');

  // The reader sees the books as borrowed.
  await signOut(page);
  await signIn(page, customer);
  await page.getByRole('button', { name: 'My Books' }).click();
  for (const title of titles) {
    await expect(page.getByText(title).first()).toBeVisible();
  }
  await expect(page.getByText('Currently Borrowed Books')).toBeVisible();

  // Returned: the books are available again.
  await signOut(page);
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: /Orders/ }).click();
  await page.getByRole('searchbox').fill(orderNumber);
  await row.getByRole('button', { name: 'Mark Returned' }).click();
  await expect(row).toContainText('Returned');
  await page.goto('/');
  await page.getByPlaceholder('Search books...').fill(titles[0]);
  await expect(bookCard(page, titles[0]).getByRole('button', { name: 'Add to Cart' })).toBeEnabled();
});

test('a book in someone else\'s order cannot be added to the cart', async ({ page, request, browser }) => {
  const [title] = await createBooks(request, `Taken ${unique()}`, 1);
  await setBatchSize(request, 1);
  try {
    // First reader orders the book.
    await registerCustomer(page);
    await page.getByPlaceholder('Search books...').fill(title);
    await bookCard(page, title).getByRole('button', { name: 'Add to Cart' }).click();
    await page.getByRole('button', { name: /^Cart/ }).click();
    await page.getByRole('button', { name: 'Proceed to Checkout' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Place Order' }).click();
    await expect(page.getByText('Order Placed!')).toBeVisible();

    // A second reader sees it as unavailable.
    const other = await (await browser.newContext()).newPage();
    await registerCustomer(other);
    await other.getByPlaceholder('Search books...').fill(title);
    await expect(bookCard(other, title).getByRole('button', { name: 'Not Available' })).toBeDisabled();
  } finally {
    await setBatchSize(request, 2);
  }
});
