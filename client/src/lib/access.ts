// The access-code gate in front of the whole site (src/proxy.ts, src/app/unlock).
//
// Server-only: imported by the proxy and the unlock server action, never by a client component,
// so the code stays out of the browser bundle.

export const ACCESS_CODE = "0000";
export const ACCESS_COOKIE = "altrix_access";
/** Cookie value set once the code is entered. Change it to make every browser enter the code again. */
export const ACCESS_TOKEN = "granted-v1";
