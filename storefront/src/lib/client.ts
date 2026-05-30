import type {
  AffiliateDashboard,
  ApiResult,
  Cart,
  Customer,
  CustomerAddress,
  PaymentMethods,
  PaymentProofInput,
  PayResult,
  Product,
  ProductCategory,
  ProductPage,
  ProductTag,
  ShippingAddress,
  ShippingQuote,
  SiteContent,
  Store,
  StoreAvailability,
} from "./types";

/**
 * Browser-side client. Every call goes through the Next.js BFF (/api/store/*) —
 * never directly to Odoo. AUTH IS COOKIE-BASED: the BFF sets an HttpOnly token
 * cookie on login and injects the Bearer header server-side, so this client
 * holds no token at all (XSS can't steal a session). Same-origin fetches send
 * the cookie automatically.
 */

import { useLocale } from "@/store/locale-store";

const BASE = "/api/store";
const JSON_HEADERS = { "Content-Type": "application/json" };

type AuthResult = { customer: Customer; is_guest?: boolean };

/** Current UI locale, sent as ?lang= so Odoo returns translated catalog content. */
function lang(): string {
  try {
    return useLocale.getState().locale;
  } catch {
    return "id";
  }
}

async function unwrap<T>(res: Response): Promise<T> {
  const json = (await res.json()) as ApiResult<T>;
  if (!res.ok || !json.ok) {
    throw new Error(json.message || json.error_code || `HTTP ${res.status}`);
  }
  return json.data as T;
}

// ---- Public catalog ----
export async function fetchCategories(): Promise<ProductCategory[]> {
  return unwrap(await fetch(`${BASE}/categories?lang=${lang()}`, { cache: "no-store" }));
}

export async function fetchProducts(params: Record<string, string | number> = {}): Promise<ProductPage> {
  const qs = new URLSearchParams(
    Object.entries({ lang: lang(), ...params }).map(([k, v]) => [k, String(v)]),
  ).toString();
  return unwrap(await fetch(`${BASE}/products?${qs}`, { cache: "no-store" }));
}

export async function fetchProduct(id: number | string): Promise<Product> {
  return unwrap(await fetch(`${BASE}/products/${id}?lang=${lang()}`, { cache: "no-store" }));
}

export async function fetchStores(): Promise<Store[]> {
  return unwrap(await fetch(`${BASE}/stores`, { cache: "no-store" }));
}

export async function fetchContent(): Promise<SiteContent> {
  return unwrap(await fetch(`${BASE}/content?lang=${lang()}`, { cache: "no-store" }));
}

export async function subscribeNewsletter(email: string): Promise<{ subscribed: boolean }> {
  return unwrap(
    await fetch(`${BASE}/newsletter`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ email }) }),
  );
}

export async function fetchAvailability(id: number | string): Promise<StoreAvailability[]> {
  return unwrap(await fetch(`${BASE}/products/${id}/availability`, { cache: "no-store" }));
}

export async function fetchTags(): Promise<ProductTag[]> {
  return unwrap(await fetch(`${BASE}/tags?lang=${lang()}`, { cache: "no-store" }));
}

// ---- Wishlist (cookie-authed) ----
export async function fetchWishlist(): Promise<Product[]> {
  return unwrap(await fetch(`${BASE}/wishlist`, { cache: "no-store" }));
}

export async function addWishlist(product_id: number): Promise<Product[]> {
  return unwrap(
    await fetch(`${BASE}/wishlist`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ product_id }) }),
  );
}

export async function removeWishlist(productTmplId: number): Promise<Product[]> {
  return unwrap(await fetch(`${BASE}/wishlist/${productTmplId}`, { method: "DELETE" }));
}

export async function moveWishlistToCart(
  productTmplId: number,
  qty = 1,
): Promise<{ cart: Cart; wishlist: Product[] }> {
  return unwrap(
    await fetch(`${BASE}/wishlist/${productTmplId}/move-to-cart`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ qty }),
    }),
  );
}

export async function moveAllWishlistToCart(): Promise<{ cart: Cart; wishlist: Product[]; moved: number }> {
  return unwrap(
    await fetch(`${BASE}/wishlist/move-all-to-cart`, { method: "POST", headers: JSON_HEADERS, body: "{}" }),
  );
}

export async function fetchShippingQuotes(
  items: { product_id: number; qty: number }[],
): Promise<ShippingQuote[]> {
  return unwrap(
    await fetch(`${BASE}/shipping/quote`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ items }) }),
  );
}

// ---- Auth (BFF sets/clears HttpOnly cookies; returns only the customer) ----
export async function register(payload: {
  name: string;
  email: string;
  password: string;
  phone?: string;
  consent_data?: boolean;
  consent_marketing?: boolean;
}): Promise<AuthResult> {
  return unwrap(
    await fetch(`${BASE}/auth/register`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) }),
  );
}

export async function login(email: string, password: string): Promise<AuthResult> {
  return unwrap(
    await fetch(`${BASE}/auth/login`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ email, password }) }),
  );
}

export async function guestLogin(email: string, name: string, consent_data: boolean): Promise<AuthResult> {
  return unwrap(
    await fetch(`${BASE}/auth/guest`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ email, name, consent_data }),
    }),
  );
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/auth/logout`, { method: "POST" });
}

// ---- Customer profile / saved addresses (cookie-authed) ----
export async function fetchMe(): Promise<{ customer: Customer; addresses: CustomerAddress[] }> {
  return unwrap(await fetch(`${BASE}/customer/me`, { cache: "no-store" }));
}

export async function createAddress(addr: ShippingAddress & { type?: string }): Promise<{ id: number }> {
  return unwrap(
    await fetch(`${BASE}/customer/addresses`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ type: "delivery", ...addr }),
    }),
  );
}

export async function updateAddress(id: number, addr: ShippingAddress & { type?: string }): Promise<{ id: number }> {
  return unwrap(
    await fetch(`${BASE}/customer/addresses/${id}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify(addr) }),
  );
}

export async function deleteAddress(id: number): Promise<{ deleted: boolean }> {
  return unwrap(await fetch(`${BASE}/customer/addresses/${id}`, { method: "DELETE" }));
}

// ---- Cart (cookie-authed) ----
export async function getCart(): Promise<Cart> {
  return unwrap(await fetch(`${BASE}/cart`, { cache: "no-store" }));
}

export async function addToCart(product_id: number, qty = 1): Promise<Cart> {
  return unwrap(
    await fetch(`${BASE}/cart/items`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ product_id, qty }) }),
  );
}

export async function setCartLineQty(lineId: number, qty: number): Promise<Cart> {
  return unwrap(
    await fetch(`${BASE}/cart/items/${lineId}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ qty }) }),
  );
}

export async function removeCartLine(lineId: number): Promise<Cart> {
  return unwrap(await fetch(`${BASE}/cart/items/${lineId}`, { method: "DELETE" }));
}

export async function setCartAddress(address: ShippingAddress): Promise<Cart> {
  return unwrap(
    await fetch(`${BASE}/cart/address`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(address) }),
  );
}

export async function setCartPickup(warehouse_id: number): Promise<Cart> {
  return unwrap(
    await fetch(`${BASE}/cart/pickup`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ warehouse_id }) }),
  );
}

export async function applyShipping(carrier_id: number): Promise<Cart> {
  return unwrap(
    await fetch(`${BASE}/cart/shipping`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ carrier_id }) }),
  );
}

export async function checkout(payload: {
  shipping_address_id?: number;
  billing_address_id?: number;
  carrier_id?: number;
  pickup_warehouse_id?: number;
  affiliate_code?: string;
  shipping_address?: ShippingAddress;
}): Promise<{ order_id: number; name: string; amount_total: number }> {
  return unwrap(
    await fetch(`${BASE}/checkout`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) }),
  );
}

/** Payment methods published to the storefront (manual transfer + gateways). */
export async function fetchPaymentMethods(): Promise<PaymentMethods> {
  return unwrap(await fetch(`${BASE}/payment/methods?lang=${lang()}`, { cache: "no-store" }));
}

export async function payOrder(orderId: number, provider_code?: string): Promise<PayResult> {
  return unwrap(
    await fetch(`${BASE}/checkout/${orderId}/pay`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(provider_code ? { provider_code } : {}),
    }),
  );
}

/** Submit a manual bank-transfer proof for an order (wire transfer). */
export async function submitPaymentProof(
  orderId: number,
  input: PaymentProofInput,
): Promise<{ proof_id: number; state: string; reference: string }> {
  return unwrap(
    await fetch(`${BASE}/checkout/${orderId}/payment-proof`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(input),
    }),
  );
}

export async function fetchOrders(): Promise<
  { order_id: number; name: string; state: string; amount_total: number; currency: string; date: string; awb_number: string | null }[]
> {
  return unwrap(await fetch(`${BASE}/orders`, { cache: "no-store" }));
}

export async function fetchOrder(id: number | string): Promise<Cart> {
  return unwrap(await fetch(`${BASE}/orders/${id}`, { cache: "no-store" }));
}

// ---- Affiliate self-serve (cookie-authed) ----
export async function fetchAffiliateMe(): Promise<AffiliateDashboard> {
  return unwrap(await fetch(`${BASE}/affiliate/me`, { cache: "no-store" }));
}

export async function applyAffiliate(): Promise<AffiliateDashboard> {
  return unwrap(await fetch(`${BASE}/affiliate/apply`, { method: "POST", headers: JSON_HEADERS, body: "{}" }));
}

export async function createAffiliateLink(name: string, target_url: string): Promise<AffiliateDashboard> {
  return unwrap(
    await fetch(`${BASE}/affiliate/links`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ name, target_url }),
    }),
  );
}

// ---- Image URL helper ----
export function imageUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  // Route Odoo image paths through the BFF image proxy so they load from the
  // storefront's own origin (with the tenant header injected server-side).
  return `/api/img${path.startsWith("/") ? path : `/${path}`}`;
}
