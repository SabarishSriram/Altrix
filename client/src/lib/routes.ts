/** Stock detail URL. Symbols such as M&M.NS need encoding. */
export const stockHref = (symbol: string) => `/stocks/${encodeURIComponent(symbol)}`;
