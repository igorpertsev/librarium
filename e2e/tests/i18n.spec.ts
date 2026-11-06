import { expect, test } from '@playwright/test';
import { registerCustomer } from '../helpers';

test('switching to Russian translates the interface and is remembered', async ({ page }) => {
  await registerCustomer(page);
  await page.getByRole('button', { name: 'Settings' }).click();
  await page.getByRole('dialog').getByRole('combobox', { name: 'Language' }).click();
  await page.getByRole('option', { name: 'Russian' }).click();
  await page.keyboard.press('Escape');

  await expect(page.locator('html')).toHaveAttribute('lang', 'ru');
  await expect(page.getByRole('heading', { name: 'Доступные книги' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Выход' })).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Доступные книги' })).toBeVisible();
});
