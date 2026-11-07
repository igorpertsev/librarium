import { expect, test } from '@playwright/test';
import { registerCustomer, signOut } from '../helpers';

test('a reader adds a passkey and then signs in with it, without a password', async ({ page }) => {
  // Chromium's virtual authenticator stands in for Face ID / Touch ID / Windows Hello.
  const devtools = await page.context().newCDPSession(page);
  await devtools.send('WebAuthn.enable');
  await devtools.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });

  const reader = await registerCustomer(page);
  await page.goto('/profile');
  const card = page.getByTestId('passkeys');
  await card.getByRole('button', { name: 'Add a passkey' }).click();
  await card.getByLabel('Name').fill('Test device');
  await card.getByLabel('Your password (to confirm it is you)').fill(reader.password);
  await card.getByRole('button', { name: 'Create passkey' }).click();
  await expect(page.getByText('Passkey added')).toBeVisible();
  await expect(card).toContainText('Test device');
  await expect(card).toContainText('not used yet');

  await signOut(page);
  await page.getByRole('button', { name: 'Sign in with a passkey' }).click();
  await expect(page).toHaveURL('/');
  await page.goto('/profile');
  await expect(page.getByTestId('passkeys')).toContainText('last used');
  await expect(page.getByText(reader.email)).toBeVisible();
});
