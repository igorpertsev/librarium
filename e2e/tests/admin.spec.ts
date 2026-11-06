import { expect, test } from '@playwright/test';
import { ADMIN, registerCustomer, signIn, unique } from '../helpers';

test('the librarian adds, edits and deletes a book', async ({ page }) => {
  const title = `Admin ${unique()}`;
  await signIn(page, ADMIN);
  await page.goto('/admin');

  await page.getByRole('button', { name: 'Add New Book' }).click();
  const form = page.getByRole('dialog');
  await form.getByLabel('Title').fill(title);
  await form.getByLabel('Author').fill('Ada Author');
  await form.getByLabel('Age Range').fill('10+');
  await form.getByLabel('Description').fill('Written by the browser tests.');
  await form.getByRole('button', { name: 'Add Book' }).click();
  await expect(page.getByText('Book added successfully')).toBeVisible();

  const row = page.getByRole('row').filter({ hasText: title });
  await expect(row).toContainText('Ada Author');

  await row.getByRole('button', { name: `Edit “${title}”` }).click();
  await form.getByLabel('Author').fill('Ada Editor');
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
