import { expect, test } from '@playwright/test';
import { ADMIN, createBook, registerCustomer, signIn, signOut, unique } from '../helpers';

test('the librarian sets a challenge; a reader joins and completes it', async ({ page, request }) => {
  const id = unique();
  const name = `Winter reading ${id}`;
  const title = `Snow book ${id}`;
  await createBook(request, { title });

  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: 'Challenges' }).click();
  const form = page.getByRole('form', { name: 'New challenge' });
  await form.getByLabel('Name (English)').fill(name);
  await form.getByLabel('Books to read').fill('1');
  await form.getByRole('button', { name: 'Create challenge' }).click();
  await expect(page.getByText('Challenge created')).toBeVisible();
  await expect(page.getByText(name)).toBeVisible();
  await signOut(page);

  const reader = await registerCustomer(page);
  await page.goto('/profile');
  const card = page.getByTestId('challenges');
  const challenge = card.getByRole('region', { name });
  await challenge.getByRole('button', { name: 'Join' }).click();
  await expect(challenge.getByText('0 / 1')).toBeVisible();

  await page.goto(`/?q=${encodeURIComponent(title)}`);
  await page.getByRole('button', { name: title, exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: "I've read it" }).click();
  await page.keyboard.press('Escape');
  await page.goto('/profile');
  await expect(challenge.getByText('1 / 1')).toBeVisible();
  await expect(challenge.getByText('Done!')).toBeVisible();
  await signOut(page);

  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: 'Challenges' }).click();
  const row = page.getByRole('listitem').filter({ hasText: name });
  await expect(row.getByText('1 taking part · 1 done')).toBeVisible();
  await row.getByRole('button', { name: 'Who takes part' }).click();
  await expect(row.getByRole('table')).toContainText('1 / 1');
  await expect(row.getByRole('table')).toContainText(reader.name);
});
