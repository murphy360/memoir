import { Link } from "react-router";

import { usePosture } from "../app/usePosture";
import { EmptyState } from "../components/EmptyState";
import { useMe } from "../auth/useMe";

/** Home. The phone's is capture first; the wide screen's is the review workspace. */
export function HomePage() {
  const me = useMe();
  const posture = usePosture();
  if (posture === "phone") {
    return (
      <section aria-labelledby="home-title" className="capture-home">
        <h1 id="home-title">Hello, {me.data?.display_name}</h1>
        <Link to="/record" className="button primary big">
          Record a memory
        </Link>
        <p className="hint">
          Tap, talk, tap again. Memoir writes it down and files it.
        </p>
        <Link to="/questions">Questions for you</Link>
      </section>
    );
  }
  return (
    <section aria-labelledby="home-title">
      <h1 id="home-title">Your family&apos;s memoir</h1>
      <EmptyState title="Nothing to review yet">
        Record a memory or add photos. The timeline, what is waiting to be
        placed and the people to name will gather here.
      </EmptyState>
    </section>
  );
}

function Soon({
  title,
  ticket,
  children,
}: {
  title: string;
  ticket: string;
  children: string;
}) {
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">{title}</h1>
      <EmptyState title="Coming soon">{`${children} (${ticket}).`}</EmptyState>
    </section>
  );
}

export function RecordPage() {
  return (
    <Soon title="Record a memory" ticket="ticket #6">
      Recording arrives next
    </Soon>
  );
}

export function TimelinePage() {
  return (
    <Soon title="Timeline" ticket="ticket #8">
      Your periods, epics and events will show here
    </Soon>
  );
}

export function QuestionsPage() {
  return (
    <Soon title="Questions for you" ticket="ticket #9">
      Follow-up questions about your stories will wait here
    </Soon>
  );
}

export function InboxPage() {
  return (
    <Soon title="Waiting to be placed" ticket="ticket #8">
      Memories and photos that are not on the timeline yet will wait here
    </Soon>
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
