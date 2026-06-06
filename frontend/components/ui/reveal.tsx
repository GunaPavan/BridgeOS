"use client";

import { motion, type MotionProps } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Subtle "fade up" entrance for marketing/list items. Triggers once on first view.
 *
 * Usage:
 *   <Reveal delay={0.1}><Card /></Reveal>
 */
export function Reveal({
  children,
  delay = 0,
  y = 14,
  className,
  ...rest
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  className?: string;
} & MotionProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-10% 0px" }}
      transition={{ duration: 0.5, ease: "easeOut", delay }}
      className={className}
      {...rest}
    >
      {children}
    </motion.div>
  );
}
