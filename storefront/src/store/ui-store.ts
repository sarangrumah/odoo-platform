"use client";

import { create } from "zustand";

interface UIState {
  /** Whether the header announcement bar is currently shown (drives the fixed
   *  header `top` offset and the main content padding so nothing overlaps). */
  announcement: boolean;
  setAnnouncement: (v: boolean) => void;
}

export const useUI = create<UIState>()((set) => ({
  announcement: false,
  setAnnouncement: (v) => set({ announcement: v }),
}));
