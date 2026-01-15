import * as React from "react";

interface AvatarProps {
  name?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = {
  sm: "h-7 w-7",
  md: "h-9 w-9",
  lg: "h-12 w-12",
};

const iconSizeClasses = {
  sm: "h-4 w-4",
  md: "h-5 w-5",
  lg: "h-6 w-6",
};

const baseAvatarClasses = `
  flex items-center justify-center rounded-full
  bg-[var(--bg-secondary)]
  text-[var(--text-muted)]
  border border-[var(--border-default)]
`;

function HumanIcon({ className }: { className: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 19.5c1.8-3.5 5-5.5 7.5-5.5s5.7 2 7.5 5.5" />
    </svg>
  );
}

function BotIcon({ className }: { className: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="5" y="7" width="14" height="10" rx="2" />
      <path d="M12 3v4" />
      <circle cx="9" cy="12" r="1" />
      <circle cx="15" cy="12" r="1" />
    </svg>
  );
}


export function Avatar({ name, size = "md", className = "" }: AvatarProps) {
  const displayName = name || "User";
  return (
    <div
      className={`
        ${baseAvatarClasses}
        ${sizeClasses[size]}
        ${className}
      `}
      title={displayName}
    >
      <HumanIcon className={iconSizeClasses[size]} />
    </div>
  );
}

/* Role-based avatar for chat transcripts */
export function RoleAvatar({ role, size = "md" }: { role: string; size?: "sm" | "md" | "lg" }) {
  const isUser = role === "user";
  return (
    <div
      className={`
        ${baseAvatarClasses}
        ${sizeClasses[size]}
      `}
    >
      {isUser ? <HumanIcon className={iconSizeClasses[size]} /> : <BotIcon className={iconSizeClasses[size]} />}
    </div>
  );
}
