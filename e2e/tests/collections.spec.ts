import { expect, test } from '@playwright/test';
import { ADMIN, API_URL, adminToken, createBook, signIn, signOut, unique } from '../helpers';

test('the librarian features a collection and a book of the month; visitors see them', async ({ page, request }) => {
  const id = unique();
  const first = `Dragon tale ${id}`;
  const second = `Dragon song ${id}`;
  await createBook(request, { title: first });
  await createBook(request, { title: second });
  const collection = `Dragons ${id}`;

  await signIn(page, ADMIN);
  await page.goto('/admin');
  await page.getByRole('tab', { name: 'Collections' }).click();
  await page.getByLabel('New collection (English title)').fill(collection);
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  const editor = page.getByRole('region', { name: collection });
  for (const title of [second, first]) {
    await editor.getByLabel('Add books').fill(title);
    await editor.getByRole('button', { name: `Add ${title}` }).click();
  }
  await editor.getByRole('button', { name: `Move ${first} up` }).click();
  await editor.getByRole('button', { name: 'Save books' }).click();
  await expect(page.getByText('Books saved')).toBeVisible();
  await editor.getByLabel('Show as a shelf on the catalogue').click();
  await editor.getByRole('button', { name: 'Save details' }).click();
  await expect(page.getByText('Collection saved')).toBeVisible();

  const pick = page.getByRole('region', { name: 'Book of the month' });
  await pick.getByLabel('Find a book').fill(second);
  await pick.getByRole('button', { name: `Add ${second}` }).click();
  await pick.getByLabel('Note (English)').fill('Our favourite this month.');
  await pick.getByRole('button', { name: 'Save book of the month' }).click();
  await expect(page.getByText('Book of the month saved')).toBeVisible();
  await signOut(page);

  try {
    await page.goto('/');
    const hero = page.getByRole('region', { name: 'Book of the month' });
    await expect(hero).toContainText(second);
    await expect(hero).toContainText('Our favourite this month.');
    const shelf = page.getByRole('region', { name: collection });
    await expect(shelf).toContainText(first);
    await shelf.getByRole('link', { name: 'See all' }).click();
    await expect(page.getByRole('heading', { level: 1, name: collection })).toBeVisible();
    const titles = page.locator('[data-slot=card] h2');
    await expect(titles).toHaveText([first, second]); // the librarian's order
  } finally {
    // Leave the shared e2e catalogue as it was for the other tests.
    const token = await adminToken(request);
    const headers = { Authorization: `Bearer ${token}` };
    await request.delete(`${API_URL}/admin/pick`, { headers });
    const all = await (await request.get(`${API_URL}/collections`)).json();
    for (const c of all as { id: string; title_en: string }[]) {
      if (c.title_en === collection) await request.delete(`${API_URL}/admin/collections/${c.id}`, { headers });
    }
  }
});
