import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "../../api/client";
import { Button } from "../../components/Button";
import { useConfirm } from "../../components/Confirm";
import { useToast } from "../../components/Toast";
import { messageOf } from "../../lib/errors";

/**
 * Delete a memory, after a plain-words confirmation. It leaves every list at once and is
 * erased for good after 30 days (requirements 10).
 */
export function DeleteMemory({
  memoryId,
  label = "Delete this memory",
  onDeleted,
}: {
  memoryId: number;
  label?: string;
  onDeleted?: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm, element } = useConfirm();
  const remove = useMutation({
    mutationFn: async () => {
      // 204 has no body: only an error answer is unwrapped (to throw it).
      const result = await api.DELETE("/api/memories/{memory_id}", {
        params: { path: { memory_id: memoryId } },
      });
      if (result.error !== undefined) unwrap(result);
    },
    onSuccess: () => {
      for (const key of ["memory", "inbox", "questions", "placement"])
        void queryClient.invalidateQueries({ queryKey: [key] });
      toast("Memory deleted.", "success");
      onDeleted?.();
    },
    onError: (error) => toast(messageOf(error), "error"),
  });
  async function ask() {
    const ok = await confirm({
      title: "Delete this memory?",
      body: "It disappears from Memoir now, recording and all, and is erased for good after 30 days.",
      confirm: "Delete it",
      danger: true,
    });
    if (ok) remove.mutate();
  }
  return (
    <>
      <Button
        variant="danger"
        busy={remove.isPending}
        onClick={() => void ask()}
      >
        {label}
      </Button>
      {element}
    </>
  );
}
