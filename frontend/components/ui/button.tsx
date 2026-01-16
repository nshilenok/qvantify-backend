import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "secondary" | "outline" | "ghost" | "destructive" | "gradient";
type Size = "default" | "sm" | "lg";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantClasses: Record<Variant, string> = {
  default: "bg-[var(--bg-primary)] text-[var(--text-primary)] hover:bg-[var(--bg-surface)] border border-[var(--border-default)]",
  secondary: "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)] border border-[var(--border-subtle)]",
  outline: "border border-[var(--border-default)] bg-transparent hover:bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
  ghost: "bg-transparent hover:bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
  destructive: "bg-red-50 text-red-700 hover:bg-red-100 border border-red-200",
  gradient: "bg-[var(--brand-primary)] text-white shadow-[var(--shadow-md)] hover:shadow-[var(--shadow-lg)]",
};

const sizeClasses: Record<Size, string> = {
  default: "h-10 px-4 text-sm",
  sm: "h-8 px-3 text-xs",
  lg: "h-11 px-6 text-base",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", type = "button", ...props }, ref) => {
    return (
      <button
        ref={ref}
        type={type}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all-base",
          "focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]/30 focus:ring-offset-2 focus:ring-offset-[var(--bg-base)]",
          "disabled:opacity-50 disabled:pointer-events-none",
          variantClasses[variant],
          sizeClasses[size],
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
