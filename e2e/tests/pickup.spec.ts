import { expect, test, type Page } from '@playwright/test';
import { ADMIN, API_URL, adminToken, createBooks, registerCustomer, setBatchSize, signIn, signOut, unique } from '../helpers';

const id = unique();
const POINT = { name: `Desk ${id}`, address: `${id} Dragon Street` };
let pointId = '';

test.beforeAll(async ({ request }) => {
  await setBatchSize(request, 1);
  const token = await adminToken(request);
  const response = await request.post(`${API_URL}/admin/pickup-points`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      ...POINT,
      hours: [0, 1, 2, 3, 4, 5, 6].map((weekday) => ({ weekday, opens: '00:00', closes: '23:59' })),
      slot_minutes: 30,
      slot_capacity: 1,
    },
  });
  expect(response.status()).toBe(201);
  pointId = (await response.json()).id;
});

test.afterAll(async ({ request }) => {
  // Orders use the point, so it is switched off; other tests order without one.
  const token = await adminToken(request);
  await request.patch(`${API_URL}/admin/pickup-points/${pointId}`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { active: false },
  });
  await setBatchSize(request, 5);
});

const bookCard = (page: Page, title: string) =>
  page.locator('[data-slot=card]').filter({ has: page.getByRole('heading', { name: title, exact: true }) });

test('readers choose where and when to pick up their order', async ({ page, request }) => {
  const [title] = await createBooks(request, `Pickup ${id}`, 1);
  const customer = await registerCustomer(page);
  await page.getByPlaceholder('Search books...').fill(title);
  await bookCard(page, title).getByRole('button', { name: 'Add to Cart' }).click();
  await page.getByRole('button', { name: /^Cart/ }).click();
  await page.getByRole('button', { name: 'Proceed to Checkout' }).click();

  // A pickup point and a time are required before the order can be placed.
  const dialog = page.getByRole('dialog');
  const place = dialog.getByRole('button', { name: 'Place Order' });
  await dialog.getByText(POINT.name).click();
  await expect(place).toBeDisabled();
  const firstTime = dialog.getByRole('group', { name: 'Time' }).getByRole('button').first();
  await firstTime.click();
  await expect(firstTime).toHaveAttribute('aria-pressed', 'true');
  const [placed] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/orders') && r.request().method() === 'POST'),
    place.click(),
  ]);
  expect(placed.status()).toBe(201);
  const order = await placed.json();
  expect(order.pickup_point.name).toBe(POINT.name);
  await expect(page.getByText('Order Placed!')).toBeVisible();

  // The reader and the librarian both see where it will be collected.
  await page.goto('/profile');
  await expect(page.getByText(`Pick up: ${POINT.name}, ${POINT.address}`)).toBeVisible();
  await signOut(page);
  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: /Orders/ }).click();
  await page.getByRole('searchbox').fill(`#${order.number}`);
  const row = page.getByRole('row').filter({ hasText: `#${order.number}` });
  await expect(row).toContainText(customer.name);
  await expect(row).toContainText(`Pick up: ${POINT.name}`);
});
