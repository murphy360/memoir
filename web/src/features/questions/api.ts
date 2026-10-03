import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { useToast } from "../../components/Toast";
import { messageOf } from "../../lib/errors";

export type Question = components["schemas"]["QuestionOut"];
export type NextQuestion = components["schemas"]["NextQuestion"];

/** Every question query starts with this key, so one invalidation refreshes them all. */
export const QUESTIONS = ["questions"] as const;

/** Record the answer: the record screen starts at once, linked to the question. */
export const answerHref = (question: Pick<Question, "id">) =>
  `/record?start=1&question=${question.id}`;

export async function loadNext(after?: number): Promise<NextQuestion> {
  return unwrap(
    await api.GET("/api/questions/next", {
      params: { query: after ? { after_memory_id: after } : {} },
    }),
  );
}

export async function loadQuestion(id: number): Promise<Question> {
  return unwrap(
    await api.GET("/api/questions/{question_id}", {
      params: { path: { question_id: id } },
    }),
  );
}

/** Dismiss a question for good: it is never asked again. */
export function useDismiss() {
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(
        await api.PATCH("/api/questions/{question_id}", {
          params: { path: { question_id: id } },
          body: { status: "dismissed" },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUESTIONS });
      toast("Memoir will not ask that again.");
    },
    onError: (error) => toast(messageOf(error), "error"),
  });
}
