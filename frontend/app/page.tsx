import { Suspense } from "react";
import InterviewClient from "./interview/InterviewClient";

export default function Home() {
  return (
    <Suspense fallback={null}>
      <InterviewClient />
    </Suspense>
  );
}
