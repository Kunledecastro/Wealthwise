"use client";

import { useSyncExternalStore } from "react";

/**
 * Chart colours, validated with the dataviz palette checker against the Wealthwise light
 * (#ffffff) and dark (#161d1a) surfaces: lightness band, chroma, colour-blind separation
 * and contrast all pass. Slot 1 = spending, slot 2 = income, in that fixed order.
 */
const LIGHT = { spending: "#2a78d6", income: "#eb6834", grid: "#e4e7e1", axis: "#5d6a62", surface: "#ffffff", cursor: "#eef0ec" };
const DARK = { spending: "#3987e5", income: "#d95926", grid: "#2c3833", axis: "#9aa8a0", surface: "#161d1a", cursor: "#1e2723" };
export type ChartTheme = typeof LIGHT;

const query = "(prefers-color-scheme: dark)";
function subscribe(cb: () => void) {
  const mq = window.matchMedia(query);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

export function useChartTheme(): ChartTheme {
  const dark = useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  );
  return dark ? DARK : LIGHT;
}
