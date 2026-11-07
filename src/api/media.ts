import { API_ORIGIN } from './client';

/** Uploaded covers are stored as paths (/media/...) and served by the backend. */
export function mediaUrl(url: string, origin = API_ORIGIN): string {
  return url.startsWith('/media/') ? `${origin}${url}` : url;
}

/** Back to the stored form, so a book saved from the form keeps the path. */
export function storedMediaUrl(url: string, origin = API_ORIGIN): string {
  return url.startsWith(`${origin}/media/`) ? url.slice(origin.length) : url;
}
