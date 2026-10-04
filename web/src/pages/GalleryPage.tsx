import { useState } from "react";

import { Button } from "../components/Button";
import { useConfirm } from "../components/Confirm";
import { DateField } from "../components/DateField";
import { EmptyState } from "../components/EmptyState";
import { ErrorText, Field } from "../components/Form";
import { useToast } from "../components/Toast";

/** The design pieces on one page, to see them together and check them by keyboard. */
export function GalleryPage() {
  const toast = useToast();
  const { confirm, element } = useConfirm();
  const [date, setDate] = useState("summer 1968");
  const [keep, setKeep] = useState(false);
  const [answer, setAnswer] = useState("");
  return (
    <section aria-labelledby="gallery-title" className="gallery">
      <h1 id="gallery-title">Design pieces</h1>
      <h2>Buttons</h2>
      <div className="row">
        <Button variant="primary">Primary</Button>
        <Button>Secondary</Button>
        <Button variant="danger">Delete</Button>
        <Button variant="ghost">Quiet</Button>
        <Button busy>Saving…</Button>
      </div>
      <h2>Fields</h2>
      <Field
        label="A labelled field"
        hint="Hints sit under the field, never inside it."
      />
      <DateField
        label="A date"
        value={date}
        onChange={setDate}
        keepTextOnly={keep}
        onKeepTextOnlyChange={setKeep}
      />
      <ErrorText error="An error reads like this." />
      <h2>Feedback</h2>
      <div className="row">
        <Button onClick={() => toast("Saved.", "success")}>
          Show a success
        </Button>
        <Button onClick={() => toast("The server said no.", "error")}>
          Show an error
        </Button>
        <Button
          onClick={async () => {
            const ok = await confirm({
              title: "Delete this period?",
              body: "Its 3 epics move to Childhood. Nothing else changes.",
              confirm: "Delete",
              danger: true,
            });
            setAnswer(ok ? "Confirmed" : "Cancelled");
          }}
        >
          Ask to confirm
        </Button>
        <output>{answer}</output>
      </div>
      {element}
      <EmptyState
        title="An empty list"
        action={<Button variant="primary">Add one</Button>}
      >
        Say why it is empty and how to fill it.
      </EmptyState>
    </section>
  );
}
