/** A copy's label: a QR code of its book page (a phone camera opens the page; the librarian's
 * scan desk reads the copy id from it). */
export function labelUrl(bookId: string, origin = window.location.origin): string {
  return `${origin}/books/${bookId}`;
}

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

/** The copy id in a scanned label, a pasted link or a typed id; null if there is none. */
export function copyIdFrom(text: string): string | null {
  const match = UUID.exec(text.trim());
  return match ? match[0].toLowerCase() : null;
}
