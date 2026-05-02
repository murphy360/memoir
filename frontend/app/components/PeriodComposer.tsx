type PeriodComposerProps = {
  isOpen: boolean;
  newPeriodTitle: string;
  setNewPeriodTitle: (value: string) => void;
  newPeriodStart: string;
  setNewPeriodStart: (value: string) => void;
  newPeriodEnd: string;
  setNewPeriodEnd: (value: string) => void;
  newPeriodSummary: string;
  setNewPeriodSummary: (value: string) => void;
  isBusy: boolean;
  createLifePeriod: () => Promise<void>;
  onCreated: () => void;
};

export function PeriodComposer({
  isOpen,
  newPeriodTitle,
  setNewPeriodTitle,
  newPeriodStart,
  setNewPeriodStart,
  newPeriodEnd,
  setNewPeriodEnd,
  newPeriodSummary,
  setNewPeriodSummary,
  isBusy,
  createLifePeriod,
  onCreated,
}: PeriodComposerProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <article className="memory" style={{ marginTop: "0.75rem" }}>
      <h3>Create Period</h3>
      <div className="lifeFormFields">
        <input
          className="directoryInput"
          type="text"
          placeholder="Period title (e.g. Birth and Early Childhood)"
          value={newPeriodTitle}
          onChange={(e) => setNewPeriodTitle(e.target.value)}
          disabled={isBusy}
        />
        <input
          className="directoryInput"
          type="text"
          placeholder="Start text (e.g. 1948)"
          value={newPeriodStart}
          onChange={(e) => setNewPeriodStart(e.target.value)}
          disabled={isBusy}
        />
        <input
          className="directoryInput"
          type="text"
          placeholder="End text (e.g. 1960)"
          value={newPeriodEnd}
          onChange={(e) => setNewPeriodEnd(e.target.value)}
          disabled={isBusy}
        />
        <textarea
          className="directoryInput"
          placeholder="Summary"
          value={newPeriodSummary}
          onChange={(e) => setNewPeriodSummary(e.target.value)}
          disabled={isBusy}
          rows={3}
        />
      </div>
      <div className="controls">
        <button
          className="primary"
          type="button"
          onClick={async () => {
            await createLifePeriod();
            onCreated();
          }}
          disabled={!newPeriodTitle.trim() || isBusy}
        >
          Create Period
        </button>
      </div>
    </article>
  );
}
