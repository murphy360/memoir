import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "../../components/Button";
import { DateField } from "../../components/DateField";
import { Field } from "../../components/Form";
import { useToast } from "../../components/Toast";
import { messageOf } from "../../lib/errors";
import {
  describe,
  placeMemory,
  placementKey,
  type PlaceIn,
  type Placement,
} from "./api";

const DECADES = [1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020];

type Props = { memoryId: number; placement: Placement; onClose: () => void };

/**
 * Where should this memory go? Memoir's suggestion first, then recent and nearby events,
 * then somewhere new with the decade a tap away. Choosing places it at once.
 */
export function PlacementSheet({ memoryId, placement, onClose }: Props) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const place = useMutation({
    mutationFn: (body: PlaceIn) => placeMemory(memoryId, body),
    onSuccess: (placed) => {
      queryClient.setQueryData(placementKey(memoryId), {
        ...placement,
        saved_to: placed.saved_to,
      });
      queryClient.invalidateQueries({ queryKey: ["inbox"] });
      queryClient.invalidateQueries({ queryKey: ["memory", memoryId] });
      toast(
        placed.saved_to ? `Saved to ${describe(placed.saved_to)}` : "Saved.",
        "success",
      );
      onClose();
    },
    onError: (error) => toast(messageOf(error), "error"),
  });
  const pick = (body: PlaceIn) => place.mutate(body);

  return (
    <section className="sheet" aria-labelledby="place-title">
      <h2 id="place-title">Where does this memory go?</h2>
      <Choices placement={placement} pick={pick} busy={place.isPending} />
      <SomewhereNew pick={pick} busy={place.isPending} />
      <Button onClick={onClose}>Cancel</Button>
    </section>
  );
}

function Choices({
  placement,
  pick,
  busy,
}: {
  placement: Placement;
  pick: (b: PlaceIn) => void;
  busy: boolean;
}) {
  const suggested = placement.suggestions.filter((s) => s.kind !== "new");
  const seen = new Set(suggested.map((s) => s.event_id));
  const more = [...placement.nearby, ...placement.recent].filter(
    (e) => !seen.has(e.id) && seen.add(e.id),
  );
  return (
    <>
      {suggested.length ? <h3>Suggested</h3> : null}
      <ul className="choices">
        {suggested.map((s) => (
          <li key={`${s.kind}-${s.event_id ?? s.period_id}`}>
            <Button
              variant="primary"
              disabled={busy}
              onClick={() =>
                pick(
                  s.event_id
                    ? { event_id: s.event_id }
                    : { period_id: s.period_id },
                )
              }
            >
              {s.label}
            </Button>{" "}
            <span className="hint">{s.reason}</span>
          </li>
        ))}
      </ul>
      {more.length ? <h3>Recent and nearby</h3> : null}
      <ul className="choices">
        {more.map((e) => (
          <li key={e.id}>
            <Button disabled={busy} onClick={() => pick({ event_id: e.id })}>
              {e.title}
              {e.date_text ? `, ${e.date_text}` : ""}
            </Button>
          </li>
        ))}
      </ul>
    </>
  );
}

function SomewhereNew({
  pick,
  busy,
}: {
  pick: (b: PlaceIn) => void;
  busy: boolean;
}) {
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState("");
  const [keep, setKeep] = useState(false);
  const decade = Number(/\b(1[89]\d|20\d)\d/.exec(when)?.[0] ?? 0);
  const startOfDecade = decade ? Math.floor(decade / 10) * 10 : 0;
  return (
    <details className="somewhere-new">
      <summary>Somewhere new</summary>
      <Field
        label="What happened"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <DateField
        label="When"
        value={when}
        onChange={setWhen}
        keepTextOnly={keep}
        onKeepTextOnlyChange={setKeep}
      />
      <p className="hint">Or tap the decade:</p>
      <div className="row decades">
        {DECADES.map((d) => (
          <Button key={d} onClick={() => setWhen(`the ${d}s`)}>
            {d}s
          </Button>
        ))}
      </div>
      <Button
        variant="primary"
        disabled={busy || !startOfDecade}
        onClick={() =>
          pick({
            new_period: {
              title: `The ${startOfDecade}s`,
              start_text: String(startOfDecade),
              end_text: String(startOfDecade + 9),
            },
            title: title || undefined,
            date_text: when,
          })
        }
      >
        Put it there
      </Button>
    </details>
  );
}
