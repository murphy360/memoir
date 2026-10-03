import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { Button } from "../../components/Button";
import { ErrorText } from "../../components/Form";
import { answerHref, loadNext, QUESTIONS, useDismiss } from "./api";

/**
 * The one question to answer now, with one Record button (requirements 8 and 16).
 * After a recording (`after`), it waits a moment for a question about what was just
 * said before offering anything else. The server stops saying "waiting" a few minutes
 * after the recording, so the asking always ends.
 */
export function NextQuestionCard({ after }: { after?: number }) {
  const next = useQuery({
    queryKey: [...QUESTIONS, "next", after ?? null],
    queryFn: () => loadNext(after),
    refetchInterval: (q) => (q.state.data?.waiting ? 3000 : false),
  });
  const dismiss = useDismiss();
  const data = next.data;
  if (next.isError) return <ErrorText error={next.error} />;
  if (!data) return null;
  if (data.waiting) {
    return (
      <p role="status" className="next-question thinking">
        Thinking of a question about what you said…
      </p>
    );
  }
  const question = data.question;
  if (!question) {
    return after ? (
      <p role="status" className="hint">
        No more questions for now. Thank you, every word is saved.
      </p>
    ) : null;
  }
  return (
    <section aria-labelledby="next-question-title" className="next-question">
      <h2 id="next-question-title">A question for you</h2>
      <p className="question-text">{question.text}</p>
      {question.about ? <p className="hint">About: {question.about}</p> : null}
      <Link to={answerHref(question)} className="button primary big">
        Record your answer
      </Link>
      <Button
        variant="ghost"
        busy={dismiss.isPending}
        onClick={() => dismiss.mutate(question.id)}
      >
        Don&apos;t ask this again
      </Button>
    </section>
  );
}
