import type { Dispatch, RefObject, SetStateAction } from "react";
import { EventAssetList } from "./EventAssetList";
import { EventCapturePanel } from "./EventCapturePanel";
import { EventLinkedMemories } from "./EventLinkedMemories";
import { UNASSIGNED_PERIOD_VALUE } from "../lib/homePageHelpers";
import type { AssetEntry, DirectoryEntry, LifeEvent, LifePeriod, MemoryEntry, Question } from "../types";

type QuestionContext = {
  question: Question;
  sourceMemory: MemoryEntry | null;
};

type PendingRecording = {
  id: string;
  audioUrl: string;
  sizeBytes: number;
  status: "recorded" | "processing" | "saved" | "failed";
  error?: string;
};

type AudioInputDevice = {
  deviceId: string;
  label: string;
};

type EventCardProps = {
  event: LifeEvent;
  mergeCandidates: LifeEvent[];
  isHighlighted: boolean;
  isOpen: boolean;
  onToggleOpen: () => Promise<void>;
  isSavingLifeStructure: boolean;
  isRecording: boolean;
  isLoading: boolean;
  deleteLifeEvent: (eventId: number) => Promise<void>;
  editingEventTitleId: number | null;
  setEditingEventTitleId: (id: number | null) => void;
  editingEventTitleValue: string;
  setEditingEventTitleValue: (value: string) => void;
  renameEvent: (eventId: number, newTitle: string) => Promise<void>;
  editingEventDateId: number | null;
  setEditingEventDateId: (id: number | null) => void;
  editingEventDateValue: string;
  setEditingEventDateValue: (value: string) => void;
  saveEventDate: (eventId: number, newDateText: string) => Promise<void>;
  editingEventLocationId: number | null;
  setEditingEventLocationId: (id: number | null) => void;
  editingEventLocationValue: string;
  setEditingEventLocationValue: (value: string) => void;
  saveEventLocation: (eventId: number, newLocation: string) => Promise<void>;
  eventMoveTargets: Record<number, string>;
  setEventMoveTargets: Dispatch<SetStateAction<Record<number, string>>>;
  moveEventToPeriod: (event: LifeEvent) => Promise<void>;
  sortedLifePeriods: LifePeriod[];
  eventMergeTargets: Record<number, string>;
  setEventMergeTargets: Dispatch<SetStateAction<Record<number, string>>>;
  mergeLifeEvent: (sourceId: number) => Promise<void>;
  eventActionId: number | null;
  summarizeEvent: (eventId: number) => Promise<void>;
  deepResearchEvent: (eventId: number) => Promise<void>;
  acceptEventResearchSuggestion: (eventId: number) => Promise<void>;
  dismissEventResearchSuggestion: (eventId: number) => Promise<void>;
  questionsForEvent: QuestionContext[];
  setActiveQuestion: (question: Question | null) => void;
  dismissQuestion: (questionId: number) => Promise<void>;
  eventCapturePanelOpenIds: Set<number>;
  setEventCapturePanelOpenIds: Dispatch<SetStateAction<Set<number>>>;
  recordingForEventId: number | null;
  audioDevices: AudioInputDevice[];
  selectedDeviceId: string;
  setSelectedDeviceId: (value: string) => void;
  audioLevel: number;
  startRecording: (forEventId?: number) => Promise<void>;
  stopRecording: () => void;
  cancelRecording: () => void;
  eventRecordingPending: Record<number, PendingRecording>;
  eventDocumentUploadingId: number | null;
  eventDocumentErrors: Record<number, string | null>;
  uploadDocumentToEvent: (file: File, eventId: number) => Promise<void>;
  eventAssetInputRef: RefObject<HTMLInputElement>;
  isUploadingAsset: boolean;
  uploadAssetToActiveEvent: (file: File) => Promise<void>;
  activeEventAssets: AssetEntry[];
  highlightedElementId: string | null;
  expandedAssetRowIds: Set<number>;
  setExpandedAssetRowIds: Dispatch<SetStateAction<Set<number>>>;
  editingAssetTitleId: number | null;
  setEditingAssetTitleId: (id: number | null) => void;
  editingAssetTitleValue: string;
  setEditingAssetTitleValue: (value: string) => void;
  assetTitleSavingId: number | null;
  saveAssetTitle: (assetId: number, eventId?: number) => Promise<void>;
  editingAssetNotesId: number | null;
  setEditingAssetNotesId: (id: number | null) => void;
  editingAssetNotesValue: string;
  setEditingAssetNotesValue: (value: string) => void;
  assetNotesSavingId: number | null;
  saveAssetNotes: (assetId: number, eventId?: number) => Promise<void>;
  resolveApiUrl: (path: string) => string;
  formatBytes: (bytes: number) => string;
  deleteAsset: (assetId: number, eventId?: number) => Promise<void>;
  timeline: MemoryEntry[];
  editingMemoryTitleId: number | null;
  setEditingMemoryTitleId: (id: number | null) => void;
  editingMemoryTitleValue: string;
  setEditingMemoryTitleValue: (value: string) => void;
  memoryTitleSavingId: number | null;
  saveMemoryTitle: (memoryId: number, eventId?: number) => Promise<void>;
  expandedMemoryRowIds: Set<number>;
  setExpandedMemoryRowIds: Dispatch<SetStateAction<Set<number>>>;
  questions: Question[];
  peopleDirectory: DirectoryEntry[];
  acceptResearchSuggestion: (memoryId: number) => Promise<void>;
  dismissResearchSuggestion: (memoryId: number) => Promise<void>;
  reanalyzeMemory: (memoryId: number) => Promise<void>;
  deleteMemory: (memoryId: number) => Promise<void>;
  assignRecorder: (memoryId: number, personId: number) => Promise<void>;
  memoryActionId: number | null;
};

export function EventCard({
  event,
  mergeCandidates,
  isHighlighted,
  isOpen,
  onToggleOpen,
  isSavingLifeStructure,
  isRecording,
  isLoading,
  deleteLifeEvent,
  editingEventTitleId,
  setEditingEventTitleId,
  editingEventTitleValue,
  setEditingEventTitleValue,
  renameEvent,
  editingEventDateId,
  setEditingEventDateId,
  editingEventDateValue,
  setEditingEventDateValue,
  saveEventDate,
  editingEventLocationId,
  setEditingEventLocationId,
  editingEventLocationValue,
  setEditingEventLocationValue,
  saveEventLocation,
  eventMoveTargets,
  setEventMoveTargets,
  moveEventToPeriod,
  sortedLifePeriods,
  eventMergeTargets,
  setEventMergeTargets,
  mergeLifeEvent,
  eventActionId,
  summarizeEvent,
  deepResearchEvent,
  acceptEventResearchSuggestion,
  dismissEventResearchSuggestion,
  questionsForEvent,
  setActiveQuestion,
  dismissQuestion,
  eventCapturePanelOpenIds,
  setEventCapturePanelOpenIds,
  recordingForEventId,
  audioDevices,
  selectedDeviceId,
  setSelectedDeviceId,
  audioLevel,
  startRecording,
  stopRecording,
  cancelRecording,
  eventRecordingPending,
  eventDocumentUploadingId,
  eventDocumentErrors,
  uploadDocumentToEvent,
  eventAssetInputRef,
  isUploadingAsset,
  uploadAssetToActiveEvent,
  activeEventAssets,
  highlightedElementId,
  expandedAssetRowIds,
  setExpandedAssetRowIds,
  editingAssetTitleId,
  setEditingAssetTitleId,
  editingAssetTitleValue,
  setEditingAssetTitleValue,
  assetTitleSavingId,
  saveAssetTitle,
  editingAssetNotesId,
  setEditingAssetNotesId,
  editingAssetNotesValue,
  setEditingAssetNotesValue,
  assetNotesSavingId,
  saveAssetNotes,
  resolveApiUrl,
  formatBytes,
  deleteAsset,
  timeline,
  editingMemoryTitleId,
  setEditingMemoryTitleId,
  editingMemoryTitleValue,
  setEditingMemoryTitleValue,
  memoryTitleSavingId,
  saveMemoryTitle,
  expandedMemoryRowIds,
  setExpandedMemoryRowIds,
  questions,
  peopleDirectory,
  acceptResearchSuggestion,
  dismissResearchSuggestion,
  reanalyzeMemory,
  deleteMemory,
  assignRecorder,
  memoryActionId,
}: EventCardProps) {
  return (
    <article
      id={`event-card-${event.id}`}
      className={`memory${isHighlighted ? " focusPulse" : ""}`}
    >
      <div className="periodSummaryRow">
        <div>
          <p className="entitySectionLabel" style={{ marginBottom: "0.2rem" }}>
            <span className="entityPill entityPillEvent">Event</span>
            <span className="entityFlowArrow">contains</span>
            <span className="entityPill entityPillMemory">Memory</span>
            <span className="entityFlowArrow">+</span>
            <span className="entityPill entityPillAsset">Assets</span>
          </p>
          {editingEventTitleId === event.id ? (
            <div className="controls" style={{ marginBottom: "0.35rem" }}>
              <input
                className="directoryInput"
                type="text"
                value={editingEventTitleValue}
                autoFocus
                onChange={(e) => setEditingEventTitleValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void renameEvent(event.id, editingEventTitleValue);
                  if (e.key === "Escape") { setEditingEventTitleId(null); setEditingEventTitleValue(""); }
                }}
                style={{ flex: 1 }}
              />
              <button className="primary" type="button" onClick={() => void renameEvent(event.id, editingEventTitleValue)} disabled={!editingEventTitleValue.trim()}>Save</button>
              <button className="secondary" type="button" onClick={() => { setEditingEventTitleId(null); setEditingEventTitleValue(""); }}>Cancel</button>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <p style={{ margin: 0, fontWeight: 700 }}>{event.title}</p>
              <button
                className="secondary"
                type="button"
                title="Edit title"
                style={{ padding: "0.1rem 0.45rem", fontSize: "0.8rem" }}
                onClick={() => { setEditingEventTitleId(event.id); setEditingEventTitleValue(event.title); }}
              >
                ✏️
              </button>
            </div>
          )}
          {editingEventDateId === event.id ? (
            <div className="controls" style={{ marginTop: "0.25rem" }}>
              <input
                className="directoryInput"
                type="text"
                value={editingEventDateValue}
                autoFocus
                placeholder="Event date text"
                onChange={(e) => setEditingEventDateValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void saveEventDate(event.id, editingEventDateValue);
                  if (e.key === "Escape") { setEditingEventDateId(null); setEditingEventDateValue(""); }
                }}
                style={{ flex: 1 }}
              />
              <button className="primary" type="button" onClick={() => void saveEventDate(event.id, editingEventDateValue)}>Save</button>
              <button className="secondary" type="button" onClick={() => { setEditingEventDateId(null); setEditingEventDateValue(""); }}>Cancel</button>
            </div>
          ) : (
            <div className="controls" style={{ justifyContent: "space-between", gap: "0.4rem", marginTop: "0.2rem" }}>
              <p className="meta" style={{ margin: 0, flex: 1 }}>
                Date: {event.event_date_text || "unknown"} | Linked assets: {event.linked_asset_count}{questionsForEvent.length > 0 && ` | Questions: ${questionsForEvent.length}`}
              </p>
              <button
                className="secondary"
                type="button"
                style={{ padding: "0.1rem 0.45rem", fontSize: "0.8rem", flexShrink: 0 }}
                onClick={() => { setEditingEventDateId(event.id); setEditingEventDateValue(event.event_date_text || ""); }}
              >
                Edit Date
              </button>
            </div>
          )}
          {editingEventLocationId === event.id ? (
            <div className="controls" style={{ marginTop: "0.25rem" }}>
              <input
                className="directoryInput"
                type="text"
                value={editingEventLocationValue}
                autoFocus
                placeholder="Location"
                onChange={(e) => setEditingEventLocationValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void saveEventLocation(event.id, editingEventLocationValue);
                  if (e.key === "Escape") { setEditingEventLocationId(null); setEditingEventLocationValue(""); }
                }}
                style={{ flex: 1 }}
              />
              <button className="primary" type="button" onClick={() => void saveEventLocation(event.id, editingEventLocationValue)}>Save</button>
              <button className="secondary" type="button" onClick={() => { setEditingEventLocationId(null); setEditingEventLocationValue(""); }}>Cancel</button>
            </div>
          ) : (
            <div className="controls" style={{ justifyContent: "space-between", gap: "0.4rem", marginTop: "0.2rem" }}>
              <p className="meta" style={{ margin: 0, flex: 1 }}>
                Location: {event.location || "-"}
              </p>
              <button
                className="secondary"
                type="button"
                style={{ padding: "0.1rem 0.45rem", fontSize: "0.8rem", flexShrink: 0 }}
                onClick={() => { setEditingEventLocationId(event.id); setEditingEventLocationValue(event.location || ""); }}
              >
                Edit Location
              </button>
            </div>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", alignItems: "stretch" }}>
          <button className="secondary" type="button" onClick={() => void onToggleOpen()}>
            {isOpen ? "Hide" : "Open"}
          </button>
          <button
            className="secondary"
            type="button"
            style={{ color: "var(--danger, #c0392b)" }}
            onClick={() => void deleteLifeEvent(event.id)}
            disabled={isSavingLifeStructure || isRecording || isLoading}
          >
            Delete
          </button>
        </div>
      </div>

      {isOpen && (
        <>
          <div className="lifeEventManagementRow" style={{ marginBottom: "0.55rem" }}>
            <select
              className="directoryInput"
              value={eventMoveTargets[event.id] || (event.period_id === null ? UNASSIGNED_PERIOD_VALUE : `${event.period_id}`)}
              onChange={(e) => setEventMoveTargets((current) => ({ ...current, [event.id]: e.target.value }))}
              disabled={isSavingLifeStructure}
            >
              <option value={UNASSIGNED_PERIOD_VALUE}>Unassigned</option>
              {sortedLifePeriods.map((periodOption) => (
                <option key={periodOption.id} value={periodOption.id}>{periodOption.title}</option>
              ))}
            </select>
            <button
              className="secondary"
              type="button"
              onClick={() => void moveEventToPeriod(event)}
              disabled={isSavingLifeStructure}
            >
              Move to Period
            </button>
          </div>
          {editingEventTitleId === event.id && (
            <div className="lifeEventManagementRow" style={{ marginBottom: "0.55rem" }}>
              <select
                className="directoryInput"
                value={eventMergeTargets[event.id] || ""}
                onChange={(e) => setEventMergeTargets((current) => ({ ...current, [event.id]: e.target.value }))}
                disabled={isSavingLifeStructure}
              >
                <option value="">Merge into another event</option>
                {mergeCandidates.filter((candidate) => candidate.id !== event.id).map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>{candidate.title}</option>
                ))}
              </select>
              <button
                className="secondary"
                type="button"
                onClick={() => void mergeLifeEvent(event.id)}
                disabled={!eventMergeTargets[event.id] || isSavingLifeStructure}
              >
                Merge Event
              </button>
              <button
                className="ghost"
                type="button"
                title="Remove event wrapper only (keeps linked memory and assets)."
                onClick={() => void deleteLifeEvent(event.id)}
                disabled={isSavingLifeStructure}
              >
                Remove Event
              </button>
            </div>
          )}
          <div className="controls" style={{ marginBottom: "0.55rem", flexWrap: "wrap" }}>
            <button
              className="secondary"
              type="button"
              onClick={() => void summarizeEvent(event.id)}
              disabled={eventActionId === event.id || isRecording || isLoading || isSavingLifeStructure}
            >
              {event.summary ? "Refresh Event Summary" : "Summarize Event"}
            </button>
            <button
              className="secondary"
              type="button"
              onClick={() => void deepResearchEvent(event.id)}
              disabled={eventActionId === event.id || isRecording || isLoading || isSavingLifeStructure}
            >
              {event.research_summary ? "Refresh Deep Research" : "Deep Research"}
            </button>
          </div>
          {event.summary && (
            <section className="researchPanel" style={{ marginBottom: "0.55rem" }}>
              <p className="researchLabel">Event Summary</p>
              <pre className="researchSummary">{event.summary}</pre>
            </section>
          )}
          {event.research_summary && (
            <section className="researchPanel" style={{ marginBottom: "0.55rem" }}>
              <p className="researchLabel">Deep Research</p>
              <pre className="researchSummary">{event.research_summary}</pre>
              {(event.research_queries || []).length > 0 && (
                <div className="researchQueries">
                  <p className="researchSubhead">Search queries used</p>
                  <div className="researchQueryList">
                    {(event.research_queries || []).map((query) => (
                      <span key={`${event.id}-query-${query}`} className="researchQueryChip">{query}</span>
                    ))}
                  </div>
                </div>
              )}
              {(event.research_sources || []).length > 0 && (
                <div className="researchSources">
                  <p className="researchSubhead">Sources</p>
                  <ul className="researchSourceList">
                    {(event.research_sources || []).map((source) => (
                      <li key={`${event.id}-source-${source.url}`}>
                        <a href={source.url} target="_blank" rel="noreferrer">
                          {source.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}
          {event.research_suggested_edit && (
            <section className="suggestionBox" style={{ marginBottom: "0.55rem" }}>
              <p className="suggestionLabel">Suggested event edits</p>
              {event.research_suggested_edit.title && (
                <p className="suggestionMeta">Title: <strong>{event.research_suggested_edit.title}</strong></p>
              )}
              {event.research_suggested_edit.event_date_text && (
                <p className="suggestionMeta">Date: <strong>{event.research_suggested_edit.event_date_text}</strong></p>
              )}
              {event.research_suggested_edit.description && (
                <p className="suggestionReasoning">Description: {event.research_suggested_edit.description}</p>
              )}
              <p className="suggestionReasoning">{event.research_suggested_edit.reasoning}</p>
              <div className="suggestionActions">
                <button
                  className="primary"
                  type="button"
                  onClick={() => void acceptEventResearchSuggestion(event.id)}
                  disabled={eventActionId === event.id || isRecording || isLoading}
                >
                  Apply
                </button>
                <button
                  className="ghost"
                  type="button"
                  onClick={() => void dismissEventResearchSuggestion(event.id)}
                  disabled={eventActionId === event.id || isRecording || isLoading}
                >
                  Dismiss
                </button>
              </div>
            </section>
          )}

          <EventLinkedMemories
            event={event}
            activeEventId={event.id}
            activeEventAssets={activeEventAssets}
            timeline={timeline}
            highlightedElementId={highlightedElementId}
            editingMemoryTitleId={editingMemoryTitleId}
            setEditingMemoryTitleId={setEditingMemoryTitleId}
            editingMemoryTitleValue={editingMemoryTitleValue}
            setEditingMemoryTitleValue={setEditingMemoryTitleValue}
            memoryTitleSavingId={memoryTitleSavingId}
            saveMemoryTitle={saveMemoryTitle}
            expandedMemoryRowIds={expandedMemoryRowIds}
            setExpandedMemoryRowIds={setExpandedMemoryRowIds}
            questions={questions}
            peopleDirectory={peopleDirectory}
            formatBytes={formatBytes}
            resolveApiUrl={resolveApiUrl}
            acceptResearchSuggestion={acceptResearchSuggestion}
            dismissResearchSuggestion={dismissResearchSuggestion}
            reanalyzeMemory={reanalyzeMemory}
            deleteMemory={deleteMemory}
            assignRecorder={assignRecorder}
            isLoading={isLoading}
            memoryActionId={memoryActionId}
            isRecording={isRecording}
          />

          {questionsForEvent.length > 0 && (
            <div className="inlineQuestionList">
              <p className="inlineQuestionListLabel">Open questions for this event</p>
              {questionsForEvent.map(({ question, sourceMemory }) => (
                <article key={question.id} className="questionCard inlineQuestionCard">
                  <p className="questionText">{question.text}</p>
                  {sourceMemory && (
                    <p className="questionSource">From: <em>{sourceMemory.event_description}</em></p>
                  )}
                  <div className="questionActions">
                    <button
                      className="primary"
                      type="button"
                      onClick={() => { setActiveQuestion(question); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                      disabled={isRecording || isLoading}
                    >
                      Answer this
                    </button>
                    <button
                      className="ghost"
                      type="button"
                      onClick={() => void dismissQuestion(question.id)}
                      disabled={isRecording || isLoading}
                    >
                      Remove
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}

          <div style={{ marginTop: "0.5rem" }}>
            <button
              className="secondary"
              type="button"
              onClick={() => setEventCapturePanelOpenIds((prev) => {
                const next = new Set(prev);
                if (next.has(event.id)) next.delete(event.id); else next.add(event.id);
                return next;
              })}
              disabled={isRecording && recordingForEventId !== event.id}
            >
              {eventCapturePanelOpenIds.has(event.id) ? "Close Add Memory" : "+ Add Memory"}
            </button>
          </div>

          {eventCapturePanelOpenIds.has(event.id) && (
            <EventCapturePanel
              eventId={event.id}
              isRecording={isRecording}
              isLoading={isLoading}
              recordingForEventId={recordingForEventId}
              audioDevices={audioDevices}
              selectedDeviceId={selectedDeviceId}
              setSelectedDeviceId={setSelectedDeviceId}
              audioLevel={audioLevel}
              startRecording={(eventId) => { void startRecording(eventId); }}
              stopRecording={stopRecording}
              cancelRecording={cancelRecording}
              eventRecordingPending={eventRecordingPending}
              eventDocumentUploadingId={eventDocumentUploadingId}
              eventDocumentErrors={eventDocumentErrors}
              uploadDocumentToEvent={(file, eventId) => { void uploadDocumentToEvent(file, eventId); }}
              eventAssetInputRef={eventAssetInputRef}
              isUploadingAsset={isUploadingAsset}
              isSavingLifeStructure={isSavingLifeStructure}
              uploadAssetToActiveEvent={(file) => { void uploadAssetToActiveEvent(file); }}
            />
          )}

          {activeEventAssets.length === 0 ? (
            <p className="meta">No assets linked to this event yet.</p>
          ) : (
            <>
              <div className="entitySectionLabel">
                <span className="entityPill entityPillAsset">Assets</span>
                Supporting files linked to this event
              </div>
              <EventAssetList
                assets={activeEventAssets}
                highlightedElementId={highlightedElementId}
                expandedAssetRowIds={expandedAssetRowIds}
                setExpandedAssetRowIds={setExpandedAssetRowIds}
                editingAssetTitleId={editingAssetTitleId}
                setEditingAssetTitleId={setEditingAssetTitleId}
                editingAssetTitleValue={editingAssetTitleValue}
                setEditingAssetTitleValue={setEditingAssetTitleValue}
                assetTitleSavingId={assetTitleSavingId}
                saveAssetTitle={saveAssetTitle}
                editingAssetNotesId={editingAssetNotesId}
                setEditingAssetNotesId={setEditingAssetNotesId}
                editingAssetNotesValue={editingAssetNotesValue}
                setEditingAssetNotesValue={setEditingAssetNotesValue}
                assetNotesSavingId={assetNotesSavingId}
                saveAssetNotes={saveAssetNotes}
                resolveApiUrl={resolveApiUrl}
                formatBytes={formatBytes}
                deleteAsset={deleteAsset}
                eventId={event.id}
              />
            </>
          )}
        </>
      )}
    </article>
  );
}
