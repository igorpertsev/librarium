import { expect, test } from '@playwright/test';
import { registerCustomer, signIn, signOut } from '../helpers';

test('a new reader registers, signs out and signs in again', async ({ page }) => {
  const customer = await registerCustomer(page);
  await expect(page.getByRole('heading', { name: 'Available Books' })).toBeVisible();

  await signOut(page);
  await signIn(page, customer);
  await page.getByRole('button', { name: 'My Books' }).click();
  await expect(page.getByText(customer.email)).toBeVisible();
});

test('a wrong password is rejected with a message', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('nobody@example.com');
  await page.getByLabel('Password', { exact: true }).fill('not-the-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toHaveText('Invalid email or password');
  await expect(page).toHaveURL('/login');
});

test('signed-out visitors are sent to the sign-in page', async ({ page }) => {
  await page.goto('/profile');
  await expect(page).toHaveURL('/login');
});

test('the session survives a page reload', async ({ page }) => {
  await registerCustomer(page);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Logout' })).toBeVisible();
  await expect(page).toHaveURL('/');
});

test('reloading right after signing out keeps the reader signed out', async ({ page }) => {
  await registerCustomer(page);
  await page.getByRole('button', { name: 'Logout' }).click();
  await expect(page).toHaveURL('/login');
  await page.reload();
  await page.goto('/profile');
  await expect(page).toHaveURL('/login');
  await expect(page.getByRole('button', { name: 'My Books' })).toHaveCount(0);
});
