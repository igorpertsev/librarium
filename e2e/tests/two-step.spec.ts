import { expect, test } from '@playwright/test';
import { registerCustomer, signOut, totpCode } from '../helpers';

test('a reader turns on two-step sign-in and signs in with a code', async ({ page }) => {
  const reader = await registerCustomer(page);
  await page.goto('/profile');
  const card = page.getByTestId('two-step');
  await card.getByRole('button', { name: 'Turn on' }).click();
  await card.getByLabel('Your password').fill(reader.password);
  await card.getByRole('button', { name: 'Continue' }).click();
  await expect(card.getByRole('img', { name: 'QR code for the authenticator app' })).toBeVisible();
  const secret = (await card.locator('code').innerText()).trim();
  await card.getByLabel('Code from the app').fill(totpCode(secret));
  await card.getByRole('button', { name: 'Turn on' }).click();
  await expect(card.getByRole('list', { name: 'Recovery codes' }).getByRole('listitem')).toHaveCount(10);
  await card.getByRole('button', { name: 'Done' }).click();
  await expect(card).toContainText('On: after your password');

  await signOut(page); // ends on the sign-in page
  await page.getByLabel('Email').fill(reader.email);
  await page.getByLabel('Password', { exact: true }).fill(reader.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  // The code used to turn it on cannot be reused; the next one is accepted.
  await page.getByLabel('Code from your authenticator app').fill(totpCode(secret, 1));
  await page.getByRole('button', { name: 'Verify' }).click();
  await expect(page).toHaveURL('/');
  await expect(page.getByRole('button', { name: 'My Books' })).toBeVisible();
});
