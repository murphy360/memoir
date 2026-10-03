import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, unwrap } from "../../api/client";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorText } from "../../components/Form";
import { answerHref, QUESTIONS, useDismiss } from "./api";

/** Questions for you: every waiting question, next first, each one tap from an answer. */
export function QuestionsPage() {
  const list = useQuery({
    queryKey: [...QUESTIONS, "for-you"],
    queryFn: async () => unwrap(await api.GET("/api/questions/for-you")),
  });
  const dismiss = useDismiss();
  const items = list.data?.items ?? [];
  return (
    <section aria-labelledby="questions-title">
      <h1 id="questions-title">Questions for you</h1>
      <p className="hint">
        Memoir asks about what you have told it. Answer any of them, in any
        order.
      </p>
      <ErrorText error={list.error} />
      {list.data && !items.length ? (
        <EmptyState title="No questions waiting">
          Record a memory and Memoir will ask about it.
        </EmptyState>
      ) : null}
      <ul className="questions">
        {items.map((q) => (
          <li key={q.id}>
            <p className="question-text">{q.text}</p>
            {q.about ? <p className="hint">About: {q.about}</p> : null}
            <div className="row">
              <Link to={answerHref(q)} className="button primary">
                Record your answer
              </Link>
              <Button
                variant="ghost"
                busy={dismiss.isPending && dismiss.variables === q.id}
                onClick={() => dismiss.mutate(q.id)}
              >
                Don&apos;t ask this again
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
