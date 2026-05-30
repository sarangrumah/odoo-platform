"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Environment, Float } from "@react-three/drei";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

// Self-hosted CC0 HDRI (Poly Haven) served from our own origin → image-based
// reflections that stay within the strict CSP (connect-src 'self'), no CDN.
const HDR = "/env/studio_small_03_1k.hdr";

// Wider than the viewport on purpose: the short ends run off the left/right
// of the hero frame (offscreen), so the rectangular cut is never seen and the
// silk needs no edge feathering → it can stay fully opaque and crisp.
const WIDTH = 30;
const HEIGHT = 5.2;
const SEG_X = 272;
const SEG_Y = 60;

/**
 * Procedural fabric-weave bump map drawn on a canvas (same-origin, no fetch →
 * CSP-safe). Fine cross-hatched threads give the silk a woven micro-texture so
 * it no longer reads as a flat plastic sheet.
 */
function makeWeaveBump(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#808080";
  ctx.fillRect(0, 0, 256, 256);
  ctx.lineWidth = 1;
  for (let i = 0; i < 256; i += 4) {
    ctx.strokeStyle = i % 8 === 0 ? "rgba(255,255,255,0.22)" : "rgba(0,0,0,0.16)";
    ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, 256); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(256, i); ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(14, 5);
  tex.anisotropy = 4;
  return tex;
}

/**
 * Editorial hero accent for Gentle Woman — a long, wide length of silk strung
 * horizontally that ripples like fabric caught in the wind. Travelling sine
 * waves run along X (amplitude eased toward the free right edge) with a gentle
 * vertical sway, woven micro-texture (bump) and feathered soft ends, finished
 * with a fabric sheen in the brand palette. Client-only (next/dynamic
 * ssr:false) so the three.js bundle never blocks SSR/SEO of the page shell.
 */
function SilkDrape() {
  const meshRef = useRef<THREE.Mesh>(null);
  // Keep the pristine flat positions so each frame displaces from rest.
  const base = useMemo(() => {
    const geom = new THREE.PlaneGeometry(WIDTH, HEIGHT, SEG_X, SEG_Y);
    return Float32Array.from(geom.attributes.position.array);
  }, []);
  const bumpMap = useMemo(makeWeaveBump, []);

  useFrame(({ clock }) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const t = clock.getElapsedTime();
    const wind = t * 2.7;
    const half = WIDTH / 2;
    const pos = mesh.geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) {
      const x = base[i * 3];
      const y = base[i * 3 + 1];
      // Amplitude with a floor so the whole visible span keeps moving (the
      // ends are offscreen, so there is no anchored edge to keep still).
      const r = (x + half) / WIDTH;
      const ramp = 0.6 + 0.4 * (r * r * (3 - 2 * r));
      const z =
        Math.sin(x * 1.3 - wind) * 0.62 * ramp +
        Math.sin(x * 2.6 - wind * 1.4 + y * 0.6) * 0.26 * ramp +  // diagonal → organic, not striped
        Math.sin(x * 5.2 - wind * 1.9) * 0.08 * ramp +            // fine flutter
        Math.cos(y * 1.4 + wind * 0.5) * 0.1;                     // vertical sway
      pos.setZ(i, z);
    }
    pos.needsUpdate = true;
    mesh.geometry.computeVertexNormals();
  });

  return (
    <Float speed={1.0} rotationIntensity={0.1} floatIntensity={0.45}>
      <mesh ref={meshRef} rotation={[-0.1, 0.16, 0.03]}>
        <planeGeometry args={[WIDTH, HEIGHT, SEG_X, SEG_Y]} />
        <meshPhysicalMaterial
          color="#b08e68"
          roughness={0.55}
          sheen={0.55}
          sheenRoughness={0.35}
          sheenColor="#f5f1ea"
          bumpMap={bumpMap}
          bumpScale={0.18}
          envMapIntensity={1.0}
          side={THREE.DoubleSide}
        />
      </mesh>
    </Float>
  );
}

export default function HeroScene() {
  return (
    <Canvas camera={{ position: [0, 0, 8.6], fov: 42 }} dpr={[1, 1.8]}>
      <ambientLight intensity={0.5} />
      <directionalLight position={[4, 6, 5]} intensity={1.1} />
      <Suspense fallback={null}>
        <SilkDrape />
        <Environment files={HDR} />
      </Suspense>
    </Canvas>
  );
}
