import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { ADMIN, registerCustomer, signIn, signOut } from '../helpers';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'];

async function expectNoViolations(page: Page, name: string) {
  // Wait for content and images, so the audit sees the finished page.
  await page.waitForLoadState('load');
  await page.waitForFunction(() => [...document.images].every((img) => img.complete));
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const summary = results.violations.map((v) => `${v.id} (${v.nodes.length}): ${v.help}`);
  expect(summary, `axe violations on ${name}`).toEqual([]);
}

test('pages have no automatically detectable accessibility problems', async ({ page }) => {
  await page.goto('/login');
  await expectNoViolations(page, 'sign-in');

  await registerCustomer(page);
  await expect(page.getByRole('heading', { name: 'Available Books' })).toBeVisible();
  await expectNoViolations(page, 'catalogue');

  await page.getByRole('button', { name: /^Cart/ }).click();
  await expectNoViolations(page, 'cart');

  await page.getByRole('button', { name: 'My Books' }).click();
  await expectNoViolations(page, 'profile');

  await signOut(page);
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await expect(page.getByText('Library Statistics')).toBeVisible();
  await expectNoViolations(page, 'admin books');
  await page.getByRole('tab', { name: /Orders/ }).click();
  await expectNoViolations(page, 'admin orders');
});

test('the dark theme has no automatically detectable accessibility problems', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('theme', 'dark'));
  await page.goto('/login');
  await expect(page.locator('html')).toHaveClass(/dark/);
  await expectNoViolations(page, 'sign-in (dark)');

  await registerCustomer(page);
  await expect(page.getByRole('heading', { name: 'Available Books' })).toBeVisible();
  await expectNoViolations(page, 'catalogue (dark)');
  await page.getByRole('button', { name: 'My Books' }).click();
  await expectNoViolations(page, 'profile (dark)');

  await signOut(page);
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await expect(page.getByText('Library Statistics')).toBeVisible();
  await expectNoViolations(page, 'admin (dark)');
  await page.getByRole('tab', { name: /Orders/ }).click();
  await expectNoViolations(page, 'admin orders (dark)');
  await page.getByRole('tab', { name: 'Reports' }).click();
  await expect(page.getByText('Orders placed')).toBeVisible();
  await expectNoViolations(page, 'admin reports (dark)');
});
