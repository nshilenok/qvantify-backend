import * as React from "react";

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "text" | "title" | "avatar" | "card" | "button";
  width?: string | number;
  height?: string | number;
}

export function Skeleton({
  variant = "text",
  width,
  height,
  className = "",
  style,
  ...props
}: SkeletonProps) {
  const baseClass = "skeleton";
  
  const variantClasses: Record<string, string> = {
    text: "h-4 w-full",
    title: "h-6 w-3/4",
    avatar: "h-10 w-10 rounded-full",
    card: "h-40 w-full rounded-xl",
    button: "h-9 w-24 rounded-lg",
  };

  const combinedStyle: React.CSSProperties = {
    ...style,
    ...(width !== undefined && { width: typeof width === "number" ? `${width}px` : width }),
    ...(height !== undefined && { height: typeof height === "number" ? `${height}px` : height }),
  };

  return (
    <div
      className={`${baseClass} ${variantClasses[variant] || ""} ${className}`}
      style={combinedStyle}
      {...props}
    />
  );
}

/* Skeleton card for project grid */
export function SkeletonProjectCard() {
  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      <div className="gradient-bar opacity-50" />
      <div className="p-5 space-y-4">
        <div className="space-y-2">
          <Skeleton variant="title" />
          <Skeleton width="50%" height={12} />
        </div>
        <div className="rounded-xl bg-[var(--bg-surface)] p-3">
          <div className="flex items-center justify-between">
            <Skeleton width={60} height={14} />
            <Skeleton width={30} height={20} />
          </div>
        </div>
        <Skeleton width="40%" height={12} />
      </div>
    </div>
  );
}

/* Skeleton for session list item */
export function SkeletonSessionItem() {
  return (
    <div className="rounded-xl bg-[var(--bg-elevated)] p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 space-y-2">
          <Skeleton width="70%" height={16} />
          <Skeleton width="50%" height={12} />
        </div>
        <Skeleton width={40} height={14} />
      </div>
      <Skeleton width="30%" height={10} />
    </div>
  );
}

/* Skeleton for transcript message */
export function SkeletonMessage({ align = "left" }: { align?: "left" | "right" }) {
  return (
    <div className={`flex ${align === "right" ? "justify-end" : "justify-start"}`}>
      <div className={`flex items-start gap-3 max-w-[80%] ${align === "right" ? "flex-row-reverse" : ""}`}>
        <Skeleton variant="avatar" className="shrink-0" />
        <div className="space-y-2 flex-1">
          <Skeleton height={60} className="rounded-2xl" />
          <Skeleton width={80} height={10} />
        </div>
      </div>
    </div>
  );
}
