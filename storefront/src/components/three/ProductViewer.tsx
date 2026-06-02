"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, PresentationControls, useTexture } from "@react-three/drei";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

// Self-hosted CC0 HDRI (Poly Haven), same-origin → CSP-safe reflections.
// Shared with the home hero so the browser caches a single file.
const HDR = "/env/studio_small_03_1k.hdr";

/**
 * Draggable 3D presentation stage for the PDP. The real product image is
 * mapped onto a gently rippling length of cloth (a sine-drape plane), so the
 * "3D View" reads as the actual garment on fabric rather than an abstract
 * placeholder. The texture is loaded same-origin via the existing /api/img
 * proxy → stays within the strict CSP (no external fetch).
 */
function ProductCloth({ image }: { image?: string }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const base = useMemo(() => {
    const geom = new THREE.PlaneGeometry(2.6, 3.4, 40, 40);
    return Float32Array.from(geom.attributes.position.array);
  }, []);

  useFrame(({ clock }) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const t = clock.getElapsedTime();
    const pos = mesh.geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) {
      const x = base[i * 3];
      const y = base[i * 3 + 1];
      const z =
        Math.sin(x * 1.8 + t * 0.8) * 0.06 +
        Math.cos(y * 1.4 + t * 0.5) * 0.05;
      pos.setZ(i, z);
    }
    pos.needsUpdate = true;
    mesh.geometry.computeVertexNormals();
  });

  return (
    <mesh ref={meshRef} castShadow rotation={[0.05, 0.2, 0]}>
      <planeGeometry args={[2.6, 3.4, 40, 40]} />
      {image ? (
        <TexturedFabric image={image} />
      ) : (
        <meshPhysicalMaterial
          color="#e7ddcf"
          roughness={0.6}
          sheen={0.6}
          sheenColor="#f5f1ea"
          envMapIntensity={0.85}
          side={THREE.DoubleSide}
        />
      )}
    </mesh>
  );
}

/** Loads the product photo as a texture (suspends while fetching). */
function TexturedFabric({ image }: { image: string }) {
  const tex = useTexture(image);
  tex.colorSpace = THREE.SRGBColorSpace;
  return (
    <meshPhysicalMaterial
      map={tex}
      roughness={0.6}
      sheen={0.6}
      sheenColor="#f5f1ea"
      envMapIntensity={0.85}
      side={THREE.DoubleSide}
    />
  );
}

export default function ProductViewer({ image }: { image?: string }) {
  return (
    <Canvas shadows camera={{ position: [0, 0, 6], fov: 40 }} dpr={[1, 1.8]}>
      <ambientLight intensity={0.55} />
      <directionalLight position={[5, 8, 5]} intensity={1.1} castShadow />
      <Suspense fallback={null}>
        <PresentationControls
          global
          rotation={[0, -0.2, 0]}
          polar={[-0.3, 0.3]}
          azimuth={[-0.8, 0.8]}
          config={{ mass: 1.5, tension: 220 }}
        >
          <ProductCloth image={image} />
        </PresentationControls>
        <ContactShadows position={[0, -1.7, 0]} opacity={0.35} scale={8} blur={2.6} />
        <Environment files={HDR} />
      </Suspense>
    </Canvas>
  );
}
