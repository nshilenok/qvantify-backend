import { Suspense } from "react";
import InterviewClient from "./InterviewClient";

export default function InterviewPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center px-10 pb-10 pt-8 text-sm text-slate-600">
          Loading interview…
        </div>
      }
    >
      <InterviewClient />
    </Suspense>
  );
}
