import * as React from "react";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function Select({
  value,
  onChange,
  options,
  placeholder = "Select...",
  disabled = false,
  className = "",
}: SelectProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  const selectedOption = options.find((o) => o.value === value);

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`
          flex w-full items-center justify-between gap-2
          rounded-xl px-3 py-2.5 text-sm font-medium
        bg-[var(--bg-primary)] border border-[var(--border-default)]
          text-[var(--text-primary)]
          transition-all-base
        hover:border-[var(--border-strong)] hover:bg-[var(--bg-surface)]
          focus:outline-none focus:ring-2 focus:ring-purple-500/50
          disabled:opacity-50 disabled:cursor-not-allowed
        `}
      >
        <span className={!selectedOption ? "text-[var(--text-muted)]" : ""}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <svg
          className={`h-4 w-4 text-[var(--text-muted)] transition-transform ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 w-full rounded-xl bg-[var(--bg-primary)] border border-[var(--border-default)] shadow-lg py-1 animate-scale-in">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className={`
                flex w-full items-center gap-2 px-3 py-2 text-sm font-medium text-left
                transition-colors
                ${
                  option.value === value
                    ? "bg-purple-50 text-purple-700"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)]"
                }
              `}
            >
              {option.value === value && (
              <svg className="h-4 w-4 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
              <span className={option.value === value ? "" : "pl-6"}>{option.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
