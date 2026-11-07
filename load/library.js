// Load test (k6) for the e2e stack: visitors browse the catalogue while readers use their
// account and cart. Run it with `pnpm load:test` (load/run.sh); never against real data.
//
// Thresholds: fewer than 1 % failed requests, 95 % of catalogue requests under 500 ms and of
// reader requests under 800 ms. k6 exits non-zero when one is missed.
import http from 'k6/http';
import { check, group, sleep } from 'k6';

const BASE = (__ENV.BASE_URL || 'http://localhost:8100') + '/api/v1';
const VISITORS = Number(__ENV.VISITORS || 20);
const READERS = Number(__ENV.READERS || 5);
const DURATION = __ENV.DURATION || '1m';
const JSON_HEADERS = { 'Content-Type': 'application/json' };
const WORDS = ['dragon', 'harry', 'war', 'love', 'space', 'дракон', 'night', 'king'];

export const options = {
  scenarios: {
    visitors: {
      executor: 'ramping-vus',
      exec: 'visitor',
      startVUs: 0,
      stages: [
        { duration: '15s', target: VISITORS },
        { duration: DURATION, target: VISITORS },
        { duration: '5s', target: 0 },
      ],
      tags: { who: 'visitor' },
    },
    readers: {
      executor: 'constant-vus',
      exec: 'reader',
      vus: READERS,
      duration: DURATION,
      startTime: '10s',
      tags: { who: 'reader' },
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{who:visitor}': ['p(95)<500'],
    'http_req_duration{who:reader}': ['p(95)<800'],
    checks: ['rate>0.99'],
  },
};

const pick = (items) => items[Math.floor(Math.random() * items.length)];

/** Books to look at, and one reader account per reader VU (made once, before the test). */
export function setup() {
  const page = http.get(`${BASE}/books?page_size=50`);
  check(page, { 'catalogue loads': (r) => r.status === 200 });
  const books = page.json('items').map((b) => b.id);
  const readers = [];
  for (let i = 0; i < READERS; i += 1) {
    const account = {
      email: `load-reader-${Date.now()}-${i}@example.com`,
      password: `Load-reader-password-${i}`,
      full_name: `Load Reader ${i}`,
      telegram: `@load_reader_${i}`,
      preferred_contact_method: 'telegram',
    };
    const made = http.post(`${BASE}/auth/register`, JSON.stringify(account), { headers: JSON_HEADERS });
    check(made, { 'reader registered': (r) => r.status === 201 });
    readers.push({ email: account.email, password: account.password });
  }
  return { books, readers };
}

export function visitor(data) {
  group('catalogue', () => {
    const list = http.get(`${BASE}/books?page=1&page_size=24&sort=${pick(['title', '-created_at', 'author'])}`);
    check(list, { 'list 200': (r) => r.status === 200 });
    const search = http.get(`${BASE}/books?q=${encodeURIComponent(pick(WORDS))}`);
    check(search, { 'search 200': (r) => r.status === 200 });
    const book = http.get(`${BASE}/books/${pick(data.books)}`);
    check(book, { 'book 200': (r) => r.status === 200 });
    http.get(`${BASE}/series`);
    http.get(`${BASE}/tags`);
  });
  sleep(1 + Math.random() * 2);
}

const tokens = {};

function token(data) {
  const me = data.readers[(__VU - 1) % data.readers.length];
  if (!tokens[me.email]) {
    const signed = http.post(`${BASE}/auth/login`, JSON.stringify(me), { headers: JSON_HEADERS });
    check(signed, { 'signed in': (r) => r.status === 200 });
    tokens[me.email] = signed.json('access_token');
  }
  return tokens[me.email];
}

export function reader(data) {
  const auth = { headers: { ...JSON_HEADERS, Authorization: `Bearer ${token(data)}` } };
  group('account', () => {
    check(http.get(`${BASE}/users/me`, auth), { 'me 200': (r) => r.status === 200 });
    check(http.get(`${BASE}/orders`, auth), { 'orders 200': (r) => r.status === 200 });
    check(http.get(`${BASE}/users/me/notifications`, auth), { 'news 200': (r) => r.status === 200 });
  });
  group('cart', () => {
    const book = pick(data.books);
    // 409: the book is taken or already in the cart; both are normal here, not failures.
    const added = http.post(`${BASE}/cart/items`, JSON.stringify({ book_id: book }), {
      ...auth,
      responseCallback: http.expectedStatuses(200, 201, 409),
    });
    check(added, { 'cart answers': (r) => [200, 201, 409].includes(r.status) });
    check(http.get(`${BASE}/cart`, auth), { 'cart 200': (r) => r.status === 200 });
    if (added.status === 200 || added.status === 201) {
      http.del(`${BASE}/cart/items/${book}`, null, auth);
    }
  });
  sleep(1 + Math.random() * 2);
}
