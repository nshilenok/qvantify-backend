import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      ref={ref}
      className={cn(
        "h-10 w-full rounded-xl px-3 py-2 text-sm font-medium",
        "bg-[var(--bg-primary)] border border-[var(--border-default)]",
        "text-[var(--text-primary)] placeholder:text-[var(--text-muted)]",
        "transition-all-base",
        "hover:border-[var(--border-strong)] hover:bg-[var(--bg-surface)]",
        "focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
});
Input.displayName = "Input";
