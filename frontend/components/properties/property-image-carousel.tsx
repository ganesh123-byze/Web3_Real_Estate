"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { pickColor } from "@/lib/charts";

type PropertyImageCarouselProps = {
  images?: string[];
  propertyId: number;
  title: string;
  className?: string;
  children?: React.ReactNode;
};

export function PropertyImageCarousel({
  images,
  propertyId,
  title,
  className,
  children,
}: PropertyImageCarouselProps) {
  const safeImages = (images ?? []).filter(Boolean);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const current = safeImages[index] ?? null;
  const hasMultiple = safeImages.length > 1;

  useEffect(() => {
    setIndex(0);
  }, [propertyId, safeImages.length]);

  useEffect(() => {
    if (!hasMultiple || paused) return;
    const timer = window.setInterval(() => {
      setIndex((value) => (value + 1) % safeImages.length);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [hasMultiple, paused, safeImages.length]);

  return (
    <motion.div
      className={cn("relative h-36 overflow-hidden", className)}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      style={
        current
          ? undefined
          : { background: `linear-gradient(135deg, ${pickColor(propertyId)} 0%, hsl(var(--card)) 100%)` }
      }
    >
      {current ? (
        <img
          key={current}
          src={current}
          alt={title}
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.02]"
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-t from-background/20 via-transparent to-transparent" />

      {hasMultiple ? (
        <div className="absolute bottom-2 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-background/35 px-2 py-1 backdrop-blur">
          {safeImages.map((_, dotIndex) => (
            <button
              type="button"
              key={dotIndex}
              aria-label={`Show image ${dotIndex + 1}`}
              className={cn(
                "h-1.5 rounded-full bg-white/70 transition-all shadow-sm",
                dotIndex === index ? "w-5 bg-white" : "w-1.5 hover:bg-white",
              )}
              onClick={(event) => {
                event.stopPropagation();
                setIndex(dotIndex);
              }}
            />
          ))}
        </div>
      ) : null}

      {children}
    </motion.div>
  );
}
