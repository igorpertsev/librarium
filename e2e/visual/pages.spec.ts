import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { ADMIN, signIn } from '../helpers';

// The main pages as a visitor, a reader and the librarian, compared with reference screenshots.
// Everything that could change between runs is held still: covers from other sites become one
// grey image, and only data from the freshly seeded e2e stack is shown.

const READER = { email: 'visual-reader@example.com', password: 'visual-reader-password' };
const GREY_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGO4BgAA9AD0ksZ2XQAAAABJRU5ErkJggg==',
  'base64',
);

test.beforeEach(async ({ page }) => {
  // Covers and anything else from other sites: a fixed grey image (or nothing), never the network.
  await page.route(/^https?:\/\/(?!localhost[:/])/, (route) =>
    route.request().resourceType() === 'image'
      ? route.fulfill({ status: 200, contentType: 'image/png', body: GREY_PNG })
      : route.abort(),
  );
});

async function ensureReader(request: APIRequestContext) {
  const response = await request.post('/api/v1/auth/register', {
    data: {
      ...READER,
      full_name: 'Vera Visual',
      telegram: '@vera_visual',
      preferred_contact_method: 'telegram',
    },
  });
  // 409: already registered by an earlier project in this run.
  expect([201, 409]).toContain(response.status());
}

async function firstBookId(request: APIRequestContext): Promise<string> {
  const response = await request.get('/api/v1/books', { params: { sort: 'title', page_size: 1 } });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).items[0].id as string;
}

/** Loaded, fonts in, every image in view decoded (the dev server never goes network-idle;
 * lazy images further down never start loading). */
async function settle(page: Page) {
  await page.waitForLoadState('load');
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() =>
    [...document.images]
      .filter((img) => {
        const box = img.getBoundingClientRect();
        return box.bottom > 0 && box.top < window.innerHeight;
      })
      .every((img) => img.complete),
  );
}

test('sign-in page', async ({ page }) => {
  await page.goto('/login');
  await settle(page);
  await expect(page).toHaveScreenshot('login.png', { fullPage: true });
});

test('catalogue for a visitor', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
  await settle(page);
  await expect(page).toHaveScreenshot('catalogue.png');
});

test('book page', async ({ page, request }) => {
  await page.goto(`/books/${await firstBookId(request)}`);
  // The book opens as a dialog over the catalogue; the catalogue behind it may still be loading,
  // so only the dialog is compared.
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await settle(page);
  await expect(dialog).toHaveScreenshot('book.png');
});

test('reader profile and cart', async ({ page, request }) => {
  await ensureReader(request);
  await signIn(page, READER);
  await page.goto('/profile');
  // The cards load their data separately: wait until each shows it, so the page has its final
  // height (otherwise the comparison catches it half-built).
  await expect(page.getByTestId('reading-log')).toContainText('0 badges');
  await expect(page.getByTestId('family')).toBeVisible();
  await expect(page.getByTestId('calendar')).toBeVisible();
  await expect(page.getByText(/haven't borrowed any books yet/)).toBeVisible();
  await settle(page);
  await expect(page).toHaveScreenshot('profile.png', { fullPage: true });
  await page.goto('/cart');
  await settle(page);
  await expect(page).toHaveScreenshot('cart.png', { fullPage: true });
});

test('librarian portal', async ({ page }) => {
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await settle(page);
  await expect(page).toHaveScreenshot('admin.png');
});
