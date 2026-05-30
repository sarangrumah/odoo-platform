export type Locale = "id" | "en";
export const LOCALES: Locale[] = ["id", "en"];
export const DEFAULT_LOCALE: Locale = "id";

type Dict = Record<string, string>;

const en: Dict = {
  "nav.shop": "Shop",
  "nav.new": "New",
  "nav.stores": "Stores",
  "plp.title": "The Collection",
  "plp.all": "All",
  "plp.price": "Price (Rp)",
  "plp.min": "Min",
  "plp.max": "Max",
  "plp.apply": "Apply",
  "plp.reset": "Reset",
  "plp.empty": "No products found.",
  "plp.loadMore": "Load more",
  "pdp.addToCart": "Add to cart",
  "pdp.soldOut": "Sold out",
  "pdp.adding": "Adding…",
  "pdp.addWishlist": "Add to wishlist",
  "pdp.savedWishlist": "Saved to wishlist",
  "pdp.share": "Share",
  "pdp.size": "Size / Variant",
  "pdp.material": "Material & Composition",
  "pdp.inStore": "Available in store",
  "pdp.available": "Available",
  "pdp.outOfStock": "Out of stock",
  "wishlist.title": "Wishlist",
  "wishlist.empty": "Your wishlist is empty.",
  "wishlist.explore": "Explore the collection",
  "wishlist.moveAll": "Move all to cart",
  "wishlist.move": "Move to cart",
  "common.loading": "Loading…",
  "checkout.delivery": "Delivery",
  "checkout.pickup": "Pickup in store",
  "checkout.placeOrder": "Place order",
  "news.placeholder": "Your email",
  "news.success": "Thank you — you're on the list.",
  "news.error": "Please enter a valid email.",
  "home.collections": "Shop by collection",
};

const id: Dict = {
  "nav.shop": "Belanja",
  "nav.new": "Baru",
  "nav.stores": "Toko",
  "plp.title": "Koleksi",
  "plp.all": "Semua",
  "plp.price": "Harga (Rp)",
  "plp.min": "Min",
  "plp.max": "Maks",
  "plp.apply": "Terapkan",
  "plp.reset": "Atur ulang",
  "plp.empty": "Produk tidak ditemukan.",
  "plp.loadMore": "Muat lebih banyak",
  "pdp.addToCart": "Tambah ke keranjang",
  "pdp.soldOut": "Habis",
  "pdp.adding": "Menambahkan…",
  "pdp.addWishlist": "Tambah ke wishlist",
  "pdp.savedWishlist": "Tersimpan di wishlist",
  "pdp.share": "Bagikan",
  "pdp.size": "Ukuran / Varian",
  "pdp.material": "Material & Komposisi",
  "pdp.inStore": "Tersedia di toko",
  "pdp.available": "Tersedia",
  "pdp.outOfStock": "Habis",
  "wishlist.title": "Wishlist",
  "wishlist.empty": "Wishlist Anda masih kosong.",
  "wishlist.explore": "Jelajahi koleksi",
  "wishlist.moveAll": "Pindahkan semua ke keranjang",
  "wishlist.move": "Pindah ke keranjang",
  "common.loading": "Memuat…",
  "checkout.delivery": "Dikirim",
  "checkout.pickup": "Ambil di toko",
  "checkout.placeOrder": "Buat pesanan",
  "news.placeholder": "Email Anda",
  "news.success": "Terima kasih — Anda sudah terdaftar.",
  "news.error": "Masukkan email yang valid.",
  "home.collections": "Belanja per koleksi",
};

const MESSAGES: Record<Locale, Dict> = { en, id };

export function translate(locale: Locale, key: string): string {
  return MESSAGES[locale]?.[key] ?? MESSAGES.en[key] ?? key;
}
