const CURRENCY = process.env.NEXT_PUBLIC_CURRENCY || "IDR";

export function formatPrice(amount: number, currency = CURRENCY): string {
  try {
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency} ${Math.round(amount).toLocaleString("id-ID")}`;
  }
}
