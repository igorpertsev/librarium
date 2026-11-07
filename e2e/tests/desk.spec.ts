import { expect, test } from '@playwright/test';
import { ADMIN, createBook, registerCustomer, setBatchSize, signIn, signOut, unique } from '../helpers';

test('labels are printed for a copy; the scan desk hands its order over and takes it back', async ({ page, request }) => {
  const title = `Desk ${unique()}`;
  await createBook(request, { title });

  // A reader orders the book.
  await setBatchSize(request, 1);
  try {
    await registerCustomer(page);
    await page.getByPlaceholder('Search books...').fill(title);
    const card = page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
    await card.getByRole('button', { name: 'Add to Cart' }).click();
    await expect(card.getByRole('button', { name: 'Pending' })).toBeVisible();
    await page.getByRole('button', { name: /^Cart/ }).click();
    await page.getByRole('button', { name: 'Proceed to Checkout' }).click();
    const [placed] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith('/orders') && r.request().method() === 'POST'),
      page.getByRole('dialog').getByRole('button', { name: 'Place Order' }).click(),
    ]);
    expect(placed.status()).toBe(201);
    await signOut(page);
  } finally {
    await setBatchSize(request, 5);
  }

  // The librarian prints its label.
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('checkbox', { name: `Select “${title}”` }).click();
  await page.getByRole('link', { name: 'Print labels' }).click();
  await expect(page).toHaveURL(/\/admin\/labels\?ids=/);
  const labels = page.getByRole('list', { name: 'Labels' }).getByRole('listitem');
  await expect(labels).toHaveCount(1);
  await expect(labels).toContainText(title);
  await expect(labels.getByRole('img', { name: `QR code for ${title}` })).toBeVisible();
  const copyId = new URL(page.url()).searchParams.get('ids') ?? '';

  // At the desk: scanning the label (a USB scanner types its link) finds the order.
  await page.goto('/admin');
  await page.getByRole('tab', { name: 'Scan desk' }).click();
  const field = page.getByLabel('Scan or paste a label');
  await field.fill(`http://localhost:4173/books/${copyId}`);
  await field.press('Enter');
  const found = page.getByRole('region', { name: title });
  await expect(found).toContainText('waiting to be handed over');
  await found.getByRole('button', { name: /Hand over order/ }).click();
  await expect(found).toContainText('On loan to');
  await found.getByRole('button', { name: /Take back order/ }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Mark Returned' }).click();
  await expect(found).toContainText('On the shelf');
});
