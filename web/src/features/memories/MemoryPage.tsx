import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";

import { api, apiBaseUrl, unwrap } from "../../api/client";
import { Button } from "../../components/Button";
import { ErrorText } from "../../components/Form";
import { useToast } from "../../components/Toast";
import { messageOf } from "../../lib/errors";
import { SavedToLine } from "../place/SavedToLine";

type Memory = Awaited<ReturnType<typeof load>>;

async function load(id: number) {
  return unwrap(
    await api.GET("/api/memories/{memory_id}", {
      params: { path: { memory_id: id } },
    }),
  );
}

const BUSY = new Set(["transcribing"]);

/** The words, in plain language about where they are. */
function TranscriptState({
  memory,
  onRetry,
}: {
  memory: Memory;
  onRetry: () => void;
}) {
  switch (memory.transcript_state) {
    case "transcribing":
      return (
        <p role="status">Writing down the words. This takes a minute or two.</p>
      );
    case "ai_off":
      return (
        <div className="warning" role="status">
          <p>
            AI is off, so Memoir cannot write down the words yet. The recording
            is safe.
          </p>
          <Button onClick={onRetry}>Write them down now</Button>
        </div>
      );
    case "failed":
      return (
        <div className="warning" role="alert">
          <p>
            Memoir could not write down the words this time. The recording is
            safe.
          </p>
          {memory.analysis_error ? (
            <p className="hint">{memory.analysis_error}</p>
          ) : null}
          <Button variant="primary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      );
    default:
      return null;
  }
}

function Transcript({ memory }: { memory: Memory }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(memory.transcript ?? "");
  const queryClient = useQueryClient();
  const toast = useToast();
  const save = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.PATCH("/api/memories/{memory_id}", {
          params: { path: { memory_id: memory.id } },
          body: { transcript: text, keep_text_only: false },
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(["memory", memory.id], saved);
      setEditing(false);
      toast("Words saved. Memoir will not change them.", "success");
    },
    onError: (error) => toast(messageOf(error), "error"),
  });
  if (!memory.transcript && !editing) return null;
  if (editing) {
    return (
      <div className="field">
        <label htmlFor="transcript">The words</label>
        <textarea
          id="transcript"
          rows={10}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="row">
          <Button
            variant="primary"
            busy={save.isPending}
            onClick={() => save.mutate()}
          >
            Save the words
          </Button>
          <Button onClick={() => setEditing(false)}>Cancel</Button>
        </div>
      </div>
    );
  }
  return (
    <section aria-labelledby="words-title">
      <h2 id="words-title">The words</h2>
      <p className="transcript">{memory.transcript}</p>
      <Button
        onClick={() => {
          setText(memory.transcript ?? "");
          setEditing(true);
        }}
      >
        Correct the words
      </Button>
    </section>
  );
}

function Recording({ id }: { id: number }) {
  const base = apiBaseUrl(window.location.origin, import.meta.env.BASE_URL);
  return (
    <audio
      controls
      preload="metadata"
      src={`${base}/api/memories/${id}/audio`}
    />
  );
}

/** What Memoir worked out from the words, and whether it could. */
function Details({ memory }: { memory: Memory }) {
  return (
    <>
      {memory.description ? <p>{memory.description}</p> : null}
      {memory.extraction_state === "needs_details" ? (
        <p className="hint">
          Memoir could not work out the details. You can add them.
        </p>
      ) : null}
    </>
  );
}

function useMemory(id: number) {
  return useQuery({
    queryKey: ["memory", id],
    queryFn: () => load(id),
    refetchInterval: (q) =>
      BUSY.has(q.state.data?.transcript_state ?? "") ? 3000 : false,
  });
}

/** One memory: its recording, its words, and what Memoir worked out from them. */
export function MemoryPage() {
  const id = Number(useParams().id);
  const queryClient = useQueryClient();
  const memory = useMemory(id);
  const retry = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/memories/{memory_id}/transcribe", {
          params: { path: { memory_id: id } },
        }),
      ),
    onSuccess: (m) => queryClient.setQueryData(["memory", id], m),
  });
  if (memory.isError) return <ErrorText error={memory.error} />;
  if (!memory.data) return <p role="status">Opening the memory…</p>;
  const m = memory.data;
  return (
    <section aria-labelledby="memory-title" className="memory">
      <h1 id="memory-title">{m.title ?? "A memory"}</h1>
      {m.date_text ? <p className="hint">{m.date_text}</p> : null}
      {m.audio_state ? <Recording id={id} /> : null}
      <TranscriptState memory={m} onRetry={() => retry.mutate()} />
      <Transcript key={m.transcript ?? ""} memory={m} />
      <Details memory={m} />
      <SavedToLine memoryId={id} />
    </section>
  );
}
