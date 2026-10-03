import {
  useMutation,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

import { useToast } from "../components/Toast";
import { messageOf } from "./errors";

type Options<TData, TVars> = {
  queryKey: QueryKey;
  mutationFn: (vars: TVars) => Promise<unknown>;
  /** The cached value as it will be once the change succeeds. */
  apply: (current: TData | undefined, vars: TVars) => TData | undefined;
  success?: string;
};

/**
 * A change that shows at once and is undone if the server refuses it. A refusal shows a
 * toast with the server's message; the cache then refetches the truth. Only this query
 * is touched: nothing else on the screen waits.
 */
export function useOptimisticMutation<TData, TVars>({
  queryKey,
  mutationFn,
  apply,
  success,
}: Options<TData, TVars>) {
  const queryClient = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn,
    onMutate: async (vars: TVars) => {
      await queryClient.cancelQueries({ queryKey });
      const before = queryClient.getQueryData<TData>(queryKey);
      queryClient.setQueryData<TData | undefined>(
        queryKey,
        apply(before, vars),
      );
      return { before };
    },
    onError: (error, _vars, context) => {
      queryClient.setQueryData(queryKey, context?.before);
      toast(messageOf(error), "error");
    },
    onSuccess: () => {
      if (success) toast(success, "success");
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey }),
  });
}
