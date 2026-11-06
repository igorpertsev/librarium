import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const API_URL = 'http://localhost:8100/api/v1';
/** Seeded by e2e/docker-compose.yml (test-only values). */
export const ADMIN = { email: 'e2e-admin@example.com', password: 'e2e-admin-password' };

export interface Customer {
  name: string;
  email: string;
  password: string;
}

export const unique = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export async function signIn(page: Page, user: { email: string; password: string }) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password', { exact: true }).fill(user.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL('/');
}

export async function signOut(page: Page) {
  await page.getByRole('button', { name: 'Logout' }).click();
  await expect(page).toHaveURL('/login');
}

/** Registers a new customer through the sign-up form; ends signed in on the catalogue. */
export async function registerCustomer(page: Page): Promise<Customer> {
  const id = unique();
  const customer = { name: `Reader ${id}`, email: `reader-${id}@example.com`, password: 'reader-password-1' };
  await page.goto('/register');
  await page.getByLabel('Full Name').fill(customer.name);
  await page.getByLabel('Email').fill(customer.email);
  await page.getByLabel('Password', { exact: true }).fill(customer.password);
  await page.getByLabel('Confirm Password').fill(customer.password);
  await page.getByLabel('Telegram', { exact: true }).fill(`@reader_${id}`);
  await page.getByRole('button', { name: 'Create Account' }).click();
  await expect(page).toHaveURL('/');
  return customer;
}

export async function adminToken(request: APIRequestContext): Promise<string> {
  const response = await request.post(`${API_URL}/auth/login`, { data: ADMIN });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token as string;
}

/** Creates available books named "<prefix> 1..n" through the admin API; returns their titles. */
export async function createBooks(request: APIRequestContext, prefix: string, count: number) {
  const token = await adminToken(request);
  const titles: string[] = [];
  for (let n = 1; n <= count; n++) {
    const title = `${prefix} ${n}`;
    const response = await request.post(`${API_URL}/admin/books`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title,
        author: 'E2E Author',
        description: 'Created by the browser tests.',
        category: 'fiction',
        age_range: '12+',
        cover_url: null,
        image_urls: [],
        isbn: null,
        publication_year: 2020,
      },
    });
    expect(response.status()).toBe(201);
    titles.push(title);
  }
  return titles;
}

/** Creates one available book through the admin API (tags by slug, series by name). */
export async function createBook(
  request: APIRequestContext,
  book: {
    title: string;
    author?: string;
    description?: string;
    language?: string;
    tags?: string[];
    series_name?: string;
    series_position?: number;
    translations?: { language: 'en' | 'ru'; title: string; author?: string; description?: string }[];
  },
) {
  const token = await adminToken(request);
  const response = await request.post(`${API_URL}/admin/books`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      author: 'E2E Author',
      description: 'Created by the browser tests.',
      category: 'fiction',
      age_range: '12+',
      cover_url: null,
      image_urls: [],
      isbn: null,
      publication_year: 2020,
      ...book,
    },
  });
  expect(response.status()).toBe(201);
}

/** Sets the batch size so a test controls how many books make an order. */
export async function setBatchSize(request: APIRequestContext, booksPerBatch: number) {
  const token = await adminToken(request);
  const response = await request.patch(`${API_URL}/admin/settings`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { books_per_batch: booksPerBatch },
  });
  expect(response.ok()).toBeTruthy();
}

/** The librarian hands an order over (status "confirmed"). */
export async function confirmOrder(request: APIRequestContext, orderId: string) {
  const token = await adminToken(request);
  const response = await request.patch(`${API_URL}/admin/orders/${orderId}/status`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { status: 'confirmed' },
  });
  expect(response.ok()).toBeTruthy();
}
