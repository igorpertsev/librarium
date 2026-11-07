import { expect, test } from '@playwright/test';
import { createBook, registerCustomer, setBatchSize, unique } from '../helpers';

test('a reader filters by language, saves a book, follows an author and a series', async ({ page, request }) => {
  const id = unique();
  const author = `Author ${id}`;
  const series = `Cycle ${id}`;
  await createBook(request, { title: `${id} one`, author, language: 'en', series_name: series, series_position: 1 });
  await createBook(request, { title: `${id} two`, author, language: 'en', series_name: series, series_position: 2 });
  await createBook(request, { title: `${id} русская`, author: `Автор ${id}`, language: 'ru' });

  await registerCustomer(page);
  const titles = page.locator('[data-slot=card] h2');

  // Language filter: only the Russian book.
  await page.goto(`/?q=${id}&sort=title`);
  await expect(titles).toHaveCount(3);
  await page.getByRole('combobox', { name: 'Language' }).click();
  await page.getByRole('option', { name: 'Russian' }).click();
  await expect(page).toHaveURL(/language=ru/);
  await expect(titles).toHaveText([`${id} русская`]);

  // Author page from a card.
  await page.goto(`/?q=${id}&sort=title`);
  await page.getByRole('link', { name: `All books by ${author}` }).first().click();
  await expect(page.getByRole('heading', { name: author, exact: true })).toBeVisible();
  await expect(titles).toHaveCount(2);

  // Series: the dialog of volume 1 offers volume 2.
  await page.getByRole('button', { name: `${id} one`, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: `Next: ${id} two` }).click();
  await expect(dialog.getByRole('heading', { name: `${id} two` })).toBeVisible();

  // Want to read: saved from the dialog, listed on the profile, removed there.
  await dialog.getByRole('button', { name: 'Want to read' }).click();
  await expect(page.getByText(`“${id} two” saved to Want to read`)).toBeVisible();
  await page.keyboard.press('Escape');
  await page.goto('/profile');
  const saved = page.locator('h3', { hasText: `${id} two` });
  await expect(saved).toBeVisible();
  await page.getByRole('button', { name: `Remove “${id} two” from Want to read` }).click();
  await expect(saved).toHaveCount(0);
});

test('a reader reserves a book for a date and cancels the reservation', async ({ page, request }) => {
  const title = `Holiday ${unique()}`;
  await createBook(request, { title });
  await registerCustomer(page);
  await page.goto(`/?q=${encodeURIComponent(title)}`);
  await page.getByRole('button', { name: title, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Reserve for a date' }).click();
  const day = new Date();
  day.setDate(day.getDate() + 14);
  const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
  await dialog.getByLabel('I want it from').fill(iso);
  await dialog.getByRole('button', { name: 'Reserve', exact: true }).click();
  await expect(dialog.getByText('Reserved for you from')).toBeVisible();
  // Kept for the reader: nobody else can borrow it any more.
  await expect(dialog.getByRole('button', { name: 'Not Available' })).toBeDisabled();
  await page.keyboard.press('Escape');

  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: 'Reserved for later' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel reservation' }).click();
  await expect(page.getByText(`Reservation of “${title}” cancelled`)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Reserved for later' })).toHaveCount(0);
});

test('a reader logs a finished book and earns the first badge', async ({ page, request }) => {
  const title = `Finished ${unique()}`;
  await createBook(request, { title });
  await registerCustomer(page);
  await page.goto(`/?q=${encodeURIComponent(title)}`);
  await page.getByRole('button', { name: title, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: "I've read it" }).click();
  await expect(page.getByText(`“${title}” added to your reading log`)).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Read', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');

  await page.goto('/profile');
  const log = page.getByTestId('reading-log');
  await expect(log).toContainText('1 this year · 1 in total · 1 badge');
  await expect(log.getByRole('listitem').filter({ hasText: 'First book' })).toContainText('Earned!');
  await expect(log).toContainText(title);
});

test("a parent adds a child and keeps the child's reading log apart", async ({ page, request }) => {
  const title = `Picture book ${unique()}`;
  await createBook(request, { title });
  await registerCustomer(page);
  await page.goto('/profile');
  const family = page.getByTestId('family');
  await family.getByLabel("Child's name").fill('Mia');
  await family.getByLabel('Year of birth').fill('2019');
  await family.getByRole('button', { name: 'Add child' }).click();
  await expect(page.getByText('Mia was added')).toBeVisible();

  // Mia's log is chosen, then the book is marked as read by her.
  const log = page.getByTestId('reading-log');
  await log.getByRole('button', { name: 'Mia' }).click();
  await page.goto(`/?q=${encodeURIComponent(title)}`);
  await page.getByRole('button', { name: title, exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Mia read it' }).click();
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Read by Mia' })).toBeVisible();
  await page.keyboard.press('Escape');

  await page.goto('/profile');
  await expect(log).toContainText(title);
  await log.getByRole('button', { name: 'Me' }).click();
  await expect(log).not.toContainText(title);
});

test('a parent finds books for a child and hears about books for older readers', async ({ page, request }) => {
  const id = unique();
  await createBook(request, { title: `${id} little`, age_range: '6+' });
  await createBook(request, { title: `${id} teen`, age_range: '14+' });
  await registerCustomer(page);
  await page.goto('/profile');
  const family = page.getByTestId('family');
  await family.getByLabel("Child's name").fill('Mia');
  await family.getByLabel('Year of birth').fill(String(new Date().getFullYear() - 7));
  await family.getByRole('button', { name: 'Add child' }).click();
  await expect(page.getByText('Mia was added')).toBeVisible();

  const heading = (title: string) => page.getByRole('heading', { name: title, exact: true });
  await page.goto(`/?q=${encodeURIComponent(id)}`);
  await expect(heading(`${id} teen`)).toBeVisible();
  const chip = page.getByRole('button', { name: 'Mia, 7' });
  await chip.click();
  await expect(chip).toHaveAttribute('aria-pressed', 'true');
  await expect(page).toHaveURL(/for_age=7/);
  await expect(heading(`${id} little`)).toBeVisible();
  await expect(heading(`${id} teen`)).toBeHidden();
  await chip.click();
  await expect(heading(`${id} teen`)).toBeVisible();

  await setBatchSize(request, 1);
  try {
    const card = page.locator('[data-slot=card]').filter({ has: heading(`${id} teen`) });
    await card.getByRole('button', { name: 'Add to Cart' }).click();
    await expect(card.getByRole('button', { name: 'Pending' })).toBeVisible();
    await page.getByRole('button', { name: /^Cart/ }).click();
    await page.getByRole('button', { name: 'Proceed to Checkout' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Who are the books for?').selectOption({ label: 'Mia' });
    const note = dialog.getByRole('status').filter({ hasText: 'marked for older readers' });
    await expect(note).toContainText('Mia is about 7');
    await expect(note).toContainText(`${id} teen (14+)`);
  } finally {
    await setBatchSize(request, 5);
  }
});

test('a reader gets a calendar link and the feed answers', async ({ page, request }) => {
  await registerCustomer(page);
  await page.getByRole('button', { name: 'My Books' }).click();
  const card = page.getByTestId('calendar');
  await card.getByRole('button', { name: 'Get calendar link' }).click();
  const link = card.getByLabel('Your calendar link');
  await expect(link).toHaveValue(/\/api\/v1\/calendar\/.+\.ics$/);
  await expect(card.getByRole('link', { name: 'Open in calendar app' })).toHaveAttribute('href', /^webcal:/);

  // Calendar apps fetch it without signing in.
  const url = await link.inputValue();
  const feed = await request.get(url);
  expect(feed.status()).toBe(200);
  expect(await feed.text()).toContain('BEGIN:VCALENDAR');

  await card.getByRole('button', { name: 'Turn off' }).click();
  await expect(card.getByRole('button', { name: 'Get calendar link' })).toBeVisible();
  expect((await request.get(url)).status()).toBe(404);
});
