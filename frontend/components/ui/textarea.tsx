import * as React from "react";
import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(({ className, ...props }, ref) => {
  return (
    <textarea
      ref={ref}
      className={cn(
        "min-h-[80px] w-full rounded-xl px-3 py-2.5 text-sm font-medium resize-none",
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
Textarea.displayName = "Textarea";
