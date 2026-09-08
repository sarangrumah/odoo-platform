"use client";

import { useEffect, useRef } from "react";

// Bundled rather than fetched from /public: it is 10 KB next to lottie's 250,
// and a static import sidesteps having to reconstruct the `/finance` basePath
// inside a client component, which has no hook for it.
import mascotData from "../../../public/mascot/mascot.json";

/**
 * The animated character.
 *
 * One Lottie file, four segments on a single timeline (see
 * scripts/gen_mascot.py for the placeholder that ships today). Swapping in a
 * designer's file means replacing public/mascot/mascot.json and nothing else,
 * as long as it keeps the same frame ranges.
 */
export type MascotState = "idle" | "listening" | "thinking" | "talking";

const SEGMENTS: Record<MascotState, [number, number]> = {
  idle: [0, 59],
  listening: [60, 119],
  thinking: [120, 179],
  talking: [180, 239],
};

/** The player type we actually use, rather than pulling in lottie's own types. */
interface Player {
  playSegments(segment: [number, number], forceFlag: boolean): void;
  goToAndStop(value: number, isFrame: boolean): void;
  destroy(): void;
  setSpeed(speed: number): void;
}

export function Mascot({ state, size = 56 }: { state: MascotState; size?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<Player | null>(null);

  useEffect(() => {
    let cancelled = false;
    const container = host.current;
    if (!container) return;

    // lottie-web is ~250 KB and touches `document` at import time, so it is
    // loaded in the effect rather than at module scope: the widget renders (and
    // the panel opens) before the animation library has finished arriving.
    import("lottie-web/build/player/lottie_light").then((mod) => {
      if (cancelled || !container) return;

      const lottie = (mod.default ?? mod) as {
        loadAnimation(opts: Record<string, unknown>): Player;
      };
      const anim = lottie.loadAnimation({
        container,
        renderer: "svg",
        loop: true,
        autoplay: true,
        animationData: mascotData,
        rendererSettings: { progressiveLoad: true, preserveAspectRatio: "xMidYMid meet" },
      });
      player.current = anim;

      // A character that never stops moving is a character somebody eventually
      // turns off. Honour the OS setting by freezing on the first frame.
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        anim.setSpeed(0);
        anim.goToAndStop(0, true);
      } else {
        anim.playSegments(SEGMENTS[state], true);
      }
    });

    return () => {
      cancelled = true;
      player.current?.destroy();
      player.current = null;
    };
    // The animation is created once; state changes are handled by the effect
    // below, so re-running this one would restart the whole player on a keypress.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!player.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    player.current.playSegments(SEGMENTS[state], true);
  }, [state]);

  return (
    <div
      ref={host}
      className="mascot"
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  );
}
