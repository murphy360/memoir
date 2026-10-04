import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorText } from "../../components/Form";
import { useUrlState } from "../../lib/urlState";

type Period = components["schemas"]["TimelinePeriod"];

function useOpen(): [Set<number>, (id: number) => void] {
  const [raw, setRaw] = useUrlState("open");
  const open = new Set(raw.split(",").filter(Boolean).map(Number));
  const toggle = (id: number) => {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setRaw([...next].sort((a, b) => a - b).join(","));
  };
  return [open, toggle];
}

function range(p: Period): string {
  if (p.start_text && p.end_text) return `${p.start_text} to ${p.end_text}`;
  return p.start_text ?? p.end_text ?? "Undated";
}

function Events({
  personId,
  periodId,
}: {
  personId: number;
  periodId: number;
}) {
  const events = useQuery({
    queryKey: ["timeline-events", personId, periodId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/people/{person_id}/events", {
          params: {
            path: { person_id: personId },
            query: { period_id: periodId },
          },
        }),
      ),
  });
  if (!events.data) return <p role="status">Loading…</p>;
  return (
    <ul className="events">
      {events.data.items.map((e) => (
        <li key={e.id}>
          <Link to={`/events/${e.id}`}>{e.title}</Link>
          {e.date_text ? <span className="hint"> {e.date_text}</span> : null}
          {e.auto_created_for_memory_id ? (
            <span className="hint"> (created for a memory)</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function PeriodCard({
  period,
  personId,
  open,
  toggle,
}: {
  period: Period;
  personId: number;
  open: boolean;
  toggle: () => void;
}) {
  return (
    <li className="period-card">
      <Button variant="ghost" aria-expanded={open} onClick={toggle}>
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>{" "}
        <strong>{period.title}</strong>
      </Button>
      <span className="hint">
        {" "}
        {range(period)} · {period.event_count} events
        {period.created_for_memory ? " · created for a memory" : ""}
      </span>
      {open ? <Events personId={personId} periodId={period.id} /> : null}
    </li>
  );
}

/** A person's life as chapters; each opens to its events. What is open is in the URL. */
export function PersonTimeline({ personId }: { personId: number }) {
  const [open, toggle] = useOpen();
  const timeline = useQuery({
    queryKey: ["timeline", personId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/people/{person_id}/timeline", {
          params: { path: { person_id: personId } },
        }),
      ),
  });
  if (timeline.isError) return <ErrorText error={timeline.error} />;
  if (!timeline.data) return <p role="status">Loading the timeline…</p>;
  const { person, periods, unplaced_events } = timeline.data;
  return (
    <section aria-labelledby="timeline-title">
      <h1 id="timeline-title">{person.name}&apos;s timeline</h1>
      {periods.length ? (
        <ul className="timeline">
          {periods.map((p) => (
            <PeriodCard
              key={p.id}
              period={p}
              personId={personId}
              open={open.has(p.id)}
              toggle={() => toggle(p.id)}
            />
          ))}
        </ul>
      ) : (
        <EmptyState title="No chapters yet">
          Record a memory: Memoir starts the timeline from the first one.
        </EmptyState>
      )}
      {unplaced_events ? (
        <p className="hint">
          {unplaced_events} events are not in a chapter yet.
        </p>
      ) : null}
    </section>
  );
}

/** /timeline: the signed-in person's own life. */
export function MyTimelinePage() {
  const me = useQuery({
    queryKey: ["me", "person"],
    queryFn: async () => unwrap(await api.GET("/api/me/person")),
  });
  if (me.isError) return <ErrorText error={me.error} />;
  if (!me.data) return <p role="status">Loading the timeline…</p>;
  return <PersonTimeline personId={me.data.id} />;
}

/** /people/:id/timeline */
export function PersonTimelinePage() {
  return <PersonTimeline personId={Number(useParams().id)} />;
}
