import { expect, test } from '@playwright/test';
import { ADMIN, registerCustomer, signIn, signOut, unique } from '../helpers';

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
