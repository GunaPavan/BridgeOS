"use client";

import { useEffect, useState } from "react";
import { useInView, useMotionValue, useSpring } from "framer-motion";
import { useRef } from "react";

/**
 * Counts up from 0 to `value` once the element scrolls into view.
 * Preserves the original formatted string at rest so SSR and a11y both work.
 */
export function AnimatedCounter({
  value,
  format = (n) => Math.round(n).toLocaleString(),
  durationMs = 1200,
  className,
}: {
  value: number;
  format?: (n: number) => string;
  durationMs?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const inView = useInView(ref, { once: true, margin: "-20% 0px" });
  const motion = useMotionValue(0);
  const spring = useSpring(motion, {
    stiffness: 60,
    damping: 18,
    duration: durationMs,
  });
  const [display, setDisplay] = useState(() => format(0));

  useEffect(() => {
    if (inView) {
      motion.set(value);
    }
  }, [inView, motion, value]);

  useEffect(() => {
    return spring.on("change", (latest) => {
      setDisplay(format(latest));
    });
  }, [spring, format]);

  return (
    <span
      ref={ref}
      className={className}
      data-testid="animated-counter"
      data-target={value}
    >
      {display}
    </span>
  );
}
