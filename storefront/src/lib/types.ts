export interface ProductCategory {
  id: number;
  name: string;
  slug: string;
  parent_id: number | null;
}

export interface ProductTag {
  id: number;
  name: string;
}

export interface ContentBlock {
  code: string;
  eyebrow: string;
  headline: string;
  body: string;
  cta_label: string;
  cta_url: string;
  image: string | null;
}

export type SiteContent = Record<string, ContentBlock>;

export interface StoreAvailability {
  store_id: number;
  store_name: string;
  city: string;
  qty: number;
  in_stock: boolean;
}

export interface ProductVariant {
  id: number;
  price: number;
  in_stock: boolean;
  attributes: { attribute: string; value: string }[];
}

export interface Product {
  id: number;
  name: string;
  slug: string;
  price: number;
  currency: string;
  summary: string;
  image: string;
  ref?: string;
  compare_at?: number | null;
  discount_pct?: number;
  is_new?: boolean;
  wishlist_id?: number;
  categories: { id: number; name: string }[];
  tags?: { id: number; name: string }[];
  in_stock: boolean;
  // detail-only
  images?: string[];
  description?: string;
  material?: string;
  variants?: ProductVariant[];
}

export interface Store {
  id: number;
  code: string;
  name: string;
  address: string;
  street: string;
  city: string;
  zip: string;
  phone: string;
  lat: number | null;
  lng: number | null;
  hours: string;
  image: string | false;
}

export interface ProductPage {
  items: Product[];
  total: number;
  page: number;
  pages: number;
  price_bounds?: { min: number; max: number };
}

export interface CartLine {
  id: number;
  product_id: number;
  name: string;
  qty: number;
  price_unit: number;
  price_subtotal: number;
  is_delivery: boolean;
  image: string;
}

export interface Cart {
  order_id: number;
  name: string;
  state: string;
  currency: string;
  amount_untaxed: number;
  amount_tax: number;
  amount_total: number;
  carrier_id: number | null;
  carrier_name: string | null;
  is_pickup: boolean;
  pickup_store_id: number | null;
  pickup_store_name: string | null;
  shipping_address: ShippingAddress | null;
  awb_number: string | null;
  awb_tracking_url: string | null;
  lines: CartLine[];
}

export interface ShippingAddress {
  name?: string;
  phone?: string;
  street?: string;
  street2?: string;
  city?: string;
  zip?: string;
}

export interface CustomerAddress {
  id: number;
  type: string;
  name: string;
  street: string | null;
  city: string | null;
  zip: string | null;
  phone: string | null;
}

export interface ShippingQuote {
  carrier_id: number;
  name: string;
  price: number;
  currency: string;
  etd_days: string | null;
  cod_supported: boolean;
  service: string | null;
}

export interface Customer {
  id: number;
  name: string;
  email: string;
  phone: string | null;
}

export interface Session {
  access: string;
  refresh: string;
  expires_in: number;
  customer: Customer;
}

export interface AffiliateLink {
  id: number;
  name: string;
  target_url: string;
  short_code: string;
  full_url: string;
  click_count: number;
}

export interface AffiliateDashboard {
  is_affiliate: boolean;
  code?: string;
  state?: string;
  commission_rate?: number;
  currency?: string;
  stats?: {
    clicks: number;
    conversions: { pending: number; approved: number; reversed: number; paid: number };
    earned: number;
    pending: number;
  };
  links?: AffiliateLink[];
}

export interface ApiResult<T> {
  ok: boolean;
  data?: T;
  error_code?: string;
  message?: string;
}

export interface PaymentMethod {
  id: number;
  code: string;
  custom_mode: string | null;
  label: string;
  type: "manual" | "redirect";
  logo: string | null;
  instructions: string;
  sandbox: boolean;
}

export interface PaymentMethods {
  default: string;
  methods: PaymentMethod[];
}

export type PayResult =
  | { type: "redirect"; redirect_url: string; reference: string; state: string }
  | { type: "manual"; reference: string; state: string; provider: string; instructions: string };

export interface PaymentProofInput {
  amount?: number;
  bank_reference?: string;
  sender_name?: string;
  paid_date?: string;
  note?: string;
  image?: string;
  filename?: string;
}

export interface ShopperMessage {
  role: "user" | "assistant";
  content: string;
  products?: Product[];
}

export interface ShopperResponse {
  reply: string;
  products: Product[];
  product_ids: number[];
  clarify: boolean;
  escalate: boolean;
  no_results: boolean;
}
