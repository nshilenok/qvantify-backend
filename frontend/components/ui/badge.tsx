import * as React from "react";
import { cn } from "@/lib/utils";

export type BadgeVariant = "default" | "success" | "warning" | "danger" | "neutral" | "gradient";

const variants: Record<BadgeVariant, string> = {
  default: "bg-purple-50 text-purple-700 border border-purple-200",
  success: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  warning: "bg-amber-50 text-amber-700 border border-amber-200",
  danger: "bg-red-50 text-red-700 border border-red-200",
  neutral: "bg-[var(--bg-secondary)] text-[var(--text-secondary)] border border-[var(--border-default)]",
  gradient: "bg-gradient-to-r from-purple-50 to-fuchsia-50 text-purple-700 border border-purple-200",
};

export const Badge = React.forwardRef<
  HTMLSpanElement,
  React.HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }
>(({ className, variant = "neutral", ...props }, ref) => (
  <span
    ref={ref}
    className={cn(
      "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
      variants[variant],
      className
    )}
    {...props}
  />
));
Badge.displayName = "Badge";
