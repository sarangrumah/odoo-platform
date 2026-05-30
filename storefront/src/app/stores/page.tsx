"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { MapPin, Phone, Clock, Navigation } from "lucide-react";
import { fetchStores } from "@/lib/client";
import type { Store } from "@/lib/types";

/** Great-circle distance in km between two lat/lng points (Haversine). */
function haversineKm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const R = 6371;
  const dLat = ((bLat - aLat) * Math.PI) / 180;
  const dLng = ((bLng - aLng) * Math.PI) / 180;
  const lat1 = (aLat * Math.PI) / 180;
  const lat2 = (bLat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(h));
}

type Located = Store & { distanceKm?: number };

export default function StoreLocatorPage() {
  const [stores, setStores] = useState<Store[]>([]);
  const [origin, setOrigin] = useState<{ lat: number; lng: number } | null>(null);
  const [geoState, setGeoState] = useState<"idle" | "locating" | "ok" | "error">("idle");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStores()
      .then(setStores)
      .catch(() => setStores([]))
      .finally(() => setLoading(false));
  }, []);

  function locateMe() {
    if (!("geolocation" in navigator)) {
      setGeoState("error");
      return;
    }
    setGeoState("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setOrigin({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoState("ok");
      },
      () => setGeoState("error"),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  const ordered: Located[] = useMemo(() => {
    if (!origin) return stores;
    return [...stores]
      .map((s) => ({
        ...s,
        distanceKm:
          s.lat != null && s.lng != null
            ? haversineKm(origin.lat, origin.lng, s.lat, s.lng)
            : undefined,
      }))
      .sort((a, b) => (a.distanceKm ?? Infinity) - (b.distanceKm ?? Infinity));
  }, [stores, origin]);

  return (
    <div className="mx-auto max-w-7xl px-6 py-16">
      <p className="eyebrow mb-4">Find Us</p>
      <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <h1 className="font-editorial text-5xl leading-tight">Store Locator</h1>
        <button
          onClick={locateMe}
          className="flex items-center gap-2 self-start bg-ink px-6 py-4 text-xs uppercase tracking-[0.2em] text-bone transition-opacity hover:opacity-90 md:self-auto"
        >
          <Navigation className="h-4 w-4" strokeWidth={1.5} />
          {geoState === "locating" ? "Locating…" : "Toko terdekat dari saya"}
        </button>
      </div>

      {geoState === "error" && (
        <p className="mt-4 text-sm text-ink/50">
          Tidak bisa mengakses lokasi. Aktifkan izin lokasi browser lalu coba lagi.
        </p>
      )}
      {geoState === "ok" && (
        <p className="mt-4 text-sm text-ink/50">Diurutkan dari yang terdekat dengan lokasi Anda.</p>
      )}

      {loading ? (
        <p className="mt-16 text-center text-ink/40">Loading…</p>
      ) : ordered.length === 0 ? (
        <p className="mt-16 text-center text-ink/40">Belum ada toko terdaftar.</p>
      ) : (
        <div className="mt-12 grid gap-px bg-ink/10 md:grid-cols-2 lg:grid-cols-3">
          {ordered.map((s, i) => (
            <motion.div
              key={s.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: i * 0.04 }}
              className="flex flex-col bg-bone p-7"
            >
              {s.image && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={`/api/img${s.image}`}
                  alt={s.name}
                  className="mb-5 aspect-[4/3] w-full object-cover"
                />
              )}
              <h2 className="font-editorial text-xl leading-snug">{s.name}</h2>

              {s.distanceKm != null && (
                <span className="mt-1 text-xs uppercase tracking-[0.18em] text-accent">
                  {s.distanceKm < 1
                    ? `${Math.round(s.distanceKm * 1000)} m`
                    : `${s.distanceKm.toFixed(1)} km`}{" "}
                  dari Anda
                </span>
              )}

              <div className="mt-4 flex items-start gap-2 text-sm text-ink/70">
                <MapPin className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.5} />
                <span>{s.address}</span>
              </div>

              {s.phone && (
                <a
                  href={`tel:${s.phone.replace(/\s/g, "")}`}
                  className="mt-2 flex items-center gap-2 text-sm text-ink/70 hover:text-accent"
                >
                  <Phone className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                  {s.phone}
                </a>
              )}

              {s.hours && (
                <div className="mt-2 flex items-start gap-2 text-sm text-ink/70">
                  <Clock className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.5} />
                  <span className="whitespace-pre-line">{s.hours}</span>
                </div>
              )}

              <a
                href={
                  s.lat != null && s.lng != null
                    ? `https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lng}`
                    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(s.name + " " + s.address)}`
                }
                target="_blank"
                rel="noopener noreferrer"
                className="mt-5 inline-block self-start border-b border-ink pb-1 text-xs uppercase tracking-[0.2em] hover:text-accent hover:border-accent"
              >
                Petunjuk arah →
              </a>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
