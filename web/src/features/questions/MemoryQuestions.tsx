import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, unwrap } from "../../api/client";
import { answerHref, loadQuestion, QUESTIONS } from "./api";

/** The question a memory answered, shown above it. */
export function AnsweredQuestion({ questionId }: { questionId: number }) {
  const question = useQuery({
    queryKey: [...QUESTIONS, questionId],
    queryFn: () => loadQuestion(questionId),
  });
  if (!question.data) return null;
  return (
    <p className="answered-question">
      Answering: <q>{question.data.text}</q>
    </p>
  );
}

/** The questions this memory raised that are still waiting, each one tap from an answer. */
export function RaisedQuestions({ memoryId }: { memoryId: number }) {
  const raised = useQuery({
    queryKey: [...QUESTIONS, "raised", memoryId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/questions", {
          params: { query: { source_memory_id: memoryId } },
        }),
      ),
  });
  const items = raised.data?.items ?? [];
  if (!items.length) return null;
  return (
    <section aria-labelledby="raised-title">
      <h2 id="raised-title">Questions this raised</h2>
      <ul className="questions">
        {items.map((q) => (
          <li key={q.id}>
            <p className="question-text">{q.text}</p>
            <Link to={answerHref(q)} className="button">
              Record your answer
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
