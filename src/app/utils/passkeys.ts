import { ApiError } from '../../api/errors';

/** Passkeys need the WebAuthn API (every current browser has it). */
export function passkeysSupported(): boolean {
  return typeof window !== 'undefined' && typeof window.PublicKeyCredential === 'function';
}

/** The browser's error when the person closed the passkey prompt (or it timed out). */
function asApiError(error: unknown): unknown {
  if (error instanceof Error && (error.name === 'NotAllowedError' || error.name === 'AbortError')) {
    return new ApiError(0, { code: 'PASSKEY_CANCELLED', message: error.message });
  }
  return error;
}

/** Ask the device for a passkey of this site (sign-in). Loaded only when used. */
export async function getPasskey(options: Record<string, unknown>): Promise<unknown> {
  const { startAuthentication } = await import('@simplewebauthn/browser');
  try {
    return await startAuthentication({ optionsJSON: options as never });
  } catch (error) {
    throw asApiError(error);
  }
}

/** Ask the device to create a passkey for this site. */
export async function createPasskey(options: Record<string, unknown>): Promise<unknown> {
  const { startRegistration } = await import('@simplewebauthn/browser');
  try {
    return await startRegistration({ optionsJSON: options as never });
  } catch (error) {
    throw asApiError(error);
  }
}
