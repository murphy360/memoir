import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, unwrap } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { ErrorText } from "../components/Form";
import { useUrlState } from "../lib/urlState";

/** People, searchable. The search lives in the URL, so reloading keeps it. */
export function PeoplePage() {
  const [q, setQ] = useUrlState("q");
  const people = useQuery({
    queryKey: ["people", q],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/people", {
          params: { query: { q: q || undefined } },
        }),
      ),
  });
  return (
    <section aria-labelledby="people-title">
      <h1 id="people-title">People</h1>
      <label className="field">
        Search by name or nickname
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      <ErrorText error={people.error} />
      {people.data?.items.length === 0 ? (
        <EmptyState title={q ? "Nobody by that name" : "No people yet"}>
          {q
            ? "Try another spelling or a nickname."
            : "People appear as stories name them."}
        </EmptyState>
      ) : (
        <ul className="list">
          {people.data?.items.map((p) => (
            <li key={p.id}>
              <Link to={`/people/${p.id}`}>{p.name}</Link>
              {p.aliases.length ? (
                <span className="hint"> ({p.aliases.join(", ")})</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** A person's page: a deep link that survives a reload. Their timeline comes later. */
export function PersonPage() {
  const id = Number(useParams().id);
  const person = useQuery({
    queryKey: ["person", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/people/{person_id}", {
          params: { path: { person_id: id } },
        }),
      ),
  });
  if (person.isError) return <ErrorText error={person.error} />;
  return (
    <section aria-labelledby="person-title">
      <h1 id="person-title">{person.data?.name ?? "…"}</h1>
      <p>
        <Link to={`/record?person=${id}&start=1`} className="button primary">
          Record a memory about {person.data?.name ?? "them"}
        </Link>
      </p>
      <p>
        <Link to="/people">All people</Link>
      </p>
    </section>
  );
}

/** An event's page: the deep link every timeline entry will point at. */
export function EventPage() {
  const id = Number(useParams().id);
  const event = useQuery({
    queryKey: ["event", id],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/events/{event_id}", {
          params: { path: { event_id: id } },
        }),
      ),
  });
  if (event.isError) return <ErrorText error={event.error} />;
  return (
    <section aria-labelledby="event-title">
      <h1 id="event-title">{event.data?.title ?? "…"}</h1>
      {event.data?.date_text ? <p>{event.data.date_text}</p> : null}
      <p>
        <Link to={`/record?event=${id}&start=1`} className="button primary">
          Add a memory to this event
        </Link>
      </p>
      <ul className="list">
        {event.data?.participants.map((p) => (
          <li key={p.person_id}>
            <Link to={`/people/${p.person_id}`}>{p.name}</Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
