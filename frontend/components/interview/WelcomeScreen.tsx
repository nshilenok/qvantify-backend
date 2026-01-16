import { useState } from "react";
import type { ProjectConfig } from "@/lib/types";

type WelcomeScreenProps = {
  project: ProjectConfig;
  isStarting: boolean;
  onStart: (payload: { email?: string; consent: boolean }) => void;
};

const textValue = (value?: string | null) => (value || "").trim();

export default function WelcomeScreen({ project, isStarting, onStart }: WelcomeScreenProps) {
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requiresEmail = Boolean(project.collect_email);
  const consentCopy = textValue(project.consent);
  const requiresConsent = Boolean(consentCopy);
  const accent = textValue(project.colour) || "#684EAD";

  const handleStart = () => {
    if (requiresEmail && !email.trim()) {
      setError("Please provide your email.");
      return;
    }
    if (requiresConsent && !consent) {
      setError("Please accept the consent to continue.");
      return;
    }
    setError(null);
    onStart({ email: email.trim() || undefined, consent: requiresConsent ? consent : true });
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col px-10 pb-10 pt-8">
      <div className="mb-10 flex flex-col gap-3">
        {project.logo && (
          <img src={project.logo} alt={project.name || "Project logo"} className="h-10 w-auto" />
        )}
        {project.welcome_title && (
          <h1 className="text-sm font-semibold text-slate-900">{textValue(project.welcome_title)}</h1>
        )}
        {project.welcome_message && (
          <p className="text-sm leading-6 text-slate-600">{project.welcome_message}</p>
        )}
        {project.welcome_second_title && (
          <p className="text-sm font-semibold text-slate-900">{project.welcome_second_title}</p>
        )}
        {project.welcome_second_message && (
          <p className="text-sm leading-6 text-slate-600">{project.welcome_second_message}</p>
        )}
      </div>

      <div className="flex flex-col gap-5">
        {requiresEmail && (
          <label className="flex flex-col gap-2 text-sm text-slate-600">
            <span className="font-semibold text-slate-900">{textValue(project.email_title)}</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={textValue(project.email_placeholder)}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-transparent focus:ring-2 focus:ring-[var(--accent)]"
            />
          </label>
        )}

        {consentCopy && (
          <label className="flex items-start gap-3 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
              className="mt-1 h-4 w-4 rounded border-slate-300 text-[var(--accent)]"
            />
            <span>{consentCopy}</span>
          </label>
        )}

        {error && <p className="text-sm leading-6 text-red-500">{error}</p>}

        <button
          type="button"
          onClick={handleStart}
          disabled={isStarting}
          className="w-fit cursor-pointer rounded px-5 py-2 text-sm font-semibold text-white shadow-sm transition disabled:cursor-not-allowed disabled:opacity-70"
          style={{ backgroundColor: accent }}
        >
          {textValue(project.cta_next)}
        </button>
      </div>
    </div>
  );
}
