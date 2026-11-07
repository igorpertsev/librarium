import { expect, test } from '@playwright/test';
import { ADMIN, createBook, createBooks, registerCustomer, signIn, signOut, unique } from '../helpers';

test('the librarian adds, edits and deletes a book', async ({ page }) => {
  const title = `Admin ${unique()}`;
  await signIn(page, ADMIN);
  await page.goto('/admin');

  await page.getByRole('button', { name: 'Add New Book' }).click();
  const form = page.getByRole('dialog');
  await form.getByLabel('Title', { exact: true }).fill(title);
  await form.getByLabel('Author', { exact: true }).fill('Ada Author');
  await form.getByLabel('Age Range').fill('10+');
  await form.getByLabel('Description', { exact: true }).fill('Written by the browser tests.');
  await form.getByRole('button', { name: 'Add Book' }).click();
  await expect(page.getByText('Book added successfully')).toBeVisible();

  const row = page.getByRole('row').filter({ hasText: title });
  await expect(row).toContainText('Ada Author');

  await row.getByRole('button', { name: `Edit “${title}”` }).click();
  await form.getByLabel('Author', { exact: true }).fill('Ada Editor');
  await form.getByRole('button', { name: 'Save Changes' }).click();
  await expect(row).toContainText('Ada Editor');

  // Deleting asks first; "Cancel" keeps the book.
  await row.getByRole('button', { name: `Delete “${title}”` }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel' }).click();
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: `Delete “${title}”` }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('Book deleted successfully')).toBeVisible();
  await expect(row).toHaveCount(0);
});

test('customers cannot open the admin portal', async ({ page }) => {
  await registerCustomer(page);
  await page.goto('/admin');
  await expect(page).toHaveURL('/');
  await expect(page.getByRole('button', { name: 'Admin Portal' })).toHaveCount(0);
});

test('an administrator makes a reader a librarian; the change is in the activity log', async ({ page }) => {
  const staff = await registerCustomer(page);
  await signOut(page);
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: /Users/ }).click();
  await page.getByRole('combobox', { name: `Role of ${staff.name}` }).click();
  await page.getByRole('option', { name: 'Librarian' }).click();
  await expect(page.getByText('User role updated successfully')).toBeVisible();
  await page.getByRole('tab', { name: 'Activity' }).click();
  const log = page.getByRole('list', { name: 'Activity log' });
  await expect(log.getByRole('listitem').first()).toContainText('Changed a user');
  await expect(log.getByRole('listitem').first()).toContainText(staff.email);
  await expect(log.getByRole('listitem').first()).toContainText('role: librarian');

  // The librarian works the desk, without settings, pickup points or the log.
  await signOut(page);
  await signIn(page, staff);
  await page.getByRole('button', { name: 'Admin Portal' }).click();
  await expect(page.getByRole('tab', { name: /Orders/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Activity' })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Pickup' })).toHaveCount(0);
  await expect(page.getByText('Batch Configuration')).toHaveCount(0);
});

test('the librarian changes several books at once', async ({ page, request }) => {
  const titles = await createBooks(request, `Bulk ${unique()}`, 2);
  await signIn(page, ADMIN);
  await page.goto('/admin');
  // Newest first: the two new books are at the top of the list.
  for (const title of titles) {
    await page.getByRole('checkbox', { name: `Select “${title}”` }).click();
  }
  const bar = page.getByRole('region', { name: 'Change selected books' });
  await expect(bar).toContainText('2 titles selected');
  await bar.getByRole('combobox', { name: 'Change' }).selectOption('status');
  await bar.getByRole('combobox', { name: 'New value' }).selectOption('not-available');
  await bar.getByRole('button', { name: 'Apply to all copies' }).click();
  await expect(page.getByText('2 titles updated')).toBeVisible();
  for (const title of titles) {
    await expect(page.getByRole('row').filter({ hasText: title })).toContainText('Not Available');
  }
  await expect(bar).toHaveCount(0);
});

test('without a camera the librarian types the ISBN in the scanner', async ({ page }) => {
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('button', { name: 'Add New Book' }).click();
  await page.getByRole('button', { name: 'Scan the ISBN barcode with the camera' }).click();
  const scanner = page.getByRole('dialog', { name: 'Scan a barcode' });
  await expect(scanner.getByRole('alert')).toBeVisible(); // no camera in the test browser
  await scanner.getByLabel('Or type the ISBN').fill('978-0-547-92822-7');
  await scanner.getByRole('button', { name: 'Use' }).click();
  await expect(scanner).toHaveCount(0);
  await expect(page.getByRole('dialog').getByLabel('ISBN', { exact: true })).toHaveValue('9780547928227');
});

test('the librarian counts the shelves', async ({ page, request }) => {
  const isbn = '9780547928227';
  await createBook(request, { title: `Shelf ${unique()}`, isbn });
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: 'Stocktaking' }).click();
  await page.getByRole('button', { name: 'Start counting' }).click();
  await page.getByRole('button', { name: 'Scan books' }).click();
  const scanner = page.getByRole('dialog', { name: 'Scan a barcode' });
  await scanner.getByLabel('Or type the ISBN').fill(isbn);
  await scanner.getByRole('button', { name: 'Use' }).click();
  await expect(scanner.getByRole('status')).toContainText(`Found ISBN ${isbn}`);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('list', { name: 'Last scans' })).toBeVisible();

  // Finish without touching the catalogue (other tests share it).
  await page.getByLabel('Mark copies not found as not available').click();
  await page.getByRole('button', { name: 'Finish counting' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Finish counting' }).click();
  await expect(page.getByText('Count finished; 0 copies marked not available')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start counting' })).toBeVisible();
});

// A 2×3 orange PNG.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAIAAAA2iEnWAAAAFElEQVR4nGN8ViHHwMDAxMDAgKAAHVABgnMd1VcAAAAASUVORK5CYII=',
  'base64',
);

test('the librarian uploads a cover for a book', async ({ page, request }) => {
  const title = `Cover ${unique()}`;
  await createBook(request, { title });
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('row').filter({ hasText: title }).getByRole('button', { name: `Edit “${title}”` }).click();
  const form = page.getByRole('dialog');
  await form.locator('#cover-file').setInputFiles({ name: 'cover.png', mimeType: 'image/png', buffer: PNG });
  await expect(page.getByText('Cover uploaded')).toBeVisible();
  const preview = form.locator('img[src*="/media/covers/"]').first();
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
});
