import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { api, unwrap } from "../../api/client";
import { loadQuestion } from "../questions/api";
import type { Context } from "./uploads";

/** Where a recording was started from, read from the address (?event=9, ?person=7...). */
export function useRecordContext(): { context: Context; autostart: boolean } {
  const [params] = useSearchParams();
  const num = (key: string) => {
    const value = Number(params.get(key));
    return Number.isInteger(value) && value > 0 ? value : undefined;
  };
  const context: Context = {
    event_id: num("event"),
    period_id: num("period"),
    person_id: num("person"),
    question_id: num("question"),
  };
  if (params.get("quick") === "1") context.quick = true;
  for (const key of Object.keys(context) as (keyof Context)[]) {
    if (context[key] === undefined) delete context[key];
  }
  return { context, autostart: params.get("start") === "1" };
}

/** A sentence saying what the recording will be added to. */
export function useContextLabel(context: Context): string | null {
  const label = useQuery({
    queryKey: ["record-context", context],
    enabled: Object.keys(context).some((k) => k !== "quick"),
    queryFn: async () => {
      if (context.event_id) {
        const e = unwrap(
          await api.GET("/api/events/{event_id}", {
            params: { path: { event_id: context.event_id } },
          }),
        );
        return `Adding to: ${e.title}`;
      }
      if (context.question_id) {
        const q = await loadQuestion(context.question_id);
        return `Answering: ${q.text}`;
      }
      if (context.period_id) {
        const p = unwrap(
          await api.GET("/api/periods/{period_id}", {
            params: { path: { period_id: context.period_id } },
          }),
        );
        return `A memory in: ${p.title}`;
      }
      if (context.person_id) {
        const p = unwrap(
          await api.GET("/api/people/{person_id}", {
            params: { path: { person_id: context.person_id } },
          }),
        );
        return `A memory about: ${p.name}`;
      }
      return null;
    },
  });
  return label.data ?? null;
}
