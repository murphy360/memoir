import { Link } from "react-router";

import { usePosture } from "../app/usePosture";
import { EmptyState } from "../components/EmptyState";
import { useMe } from "../auth/useMe";
import { NextQuestionCard } from "../features/questions/NextQuestionCard";
import { PendingUploads } from "../features/record/UploadStatus";
import { useUploads } from "../features/record/useUploads";

/** One tap from home: the record screen starts at once, filed as a quick memory. */
export const QUICK_RECORD = "/record?start=1&quick=1";

/** Home. The phone's is capture first; the wide screen's is the review workspace. */
export function HomePage() {
  const me = useMe();
  const posture = usePosture();
  const all = useUploads();
  if (posture === "phone") {
    return (
      <section aria-labelledby="home-title" className="capture-home">
        <h1 id="home-title">Hello, {me.data?.display_name}</h1>
        <Link to={QUICK_RECORD} className="button primary big">
          Record a memory
        </Link>
        <p className="hint">
          Tap, talk, tap again. Memoir writes it down and files it.
        </p>
        <NextQuestionCard />
        <Link to="/questions">All questions for you</Link>
        <PendingUploads all={all} />
      </section>
    );
  }
  return (
    <section aria-labelledby="home-title">
      <h1 id="home-title">Your family&apos;s memoir</h1>
      <NextQuestionCard />
      <p>
        <Link to="/questions">All questions for you</Link>
      </p>
      <EmptyState title="Nothing to review yet">
        Record a memory or add photos. The timeline, what is waiting to be
        placed and the people to name will gather here.
      </EmptyState>
    </section>
  );
}

export function NotFoundPage() {
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">Not here</h1>
      <p>
        There is no page at this address. <Link to="/">Go home</Link>.
      </p>
    </section>
  );
}
