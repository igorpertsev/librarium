import { describe, expect, it } from 'vitest';
import { base64UrlToBytes } from './push';

describe('base64UrlToBytes', () => {
  it('decodes base64url without padding', () => {
    expect(Array.from(base64UrlToBytes('AQID_-8'))).toEqual([1, 2, 3, 255, 239]);
  });

  it('decodes a 65-byte VAPID public key', () => {
    const key = 'BP' + 'A'.repeat(85);
    const bytes = base64UrlToBytes(key);
    expect(bytes.length).toBe(65);
    expect(bytes[0]).toBe(4);
  });
});
