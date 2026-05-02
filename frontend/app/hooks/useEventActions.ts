import { useState } from "react";
import {
  applyEventResearchSuggestionById,
  dismissEventResearchSuggestionById,
  researchEventById,
  summarizeEventById,
} from "../lib/memoirApi";

type UseEventActionsArgs = {
  activeEventId: number | null;
  loadTimeline: () => Promise<unknown>;
  loadAssetsForEvent: (eventId: number) => Promise<void>;
  setStatus: (value: string) => void;
};

export function useEventActions({
  activeEventId,
  loadTimeline,
  loadAssetsForEvent,
  setStatus,
}: UseEventActionsArgs) {
  const [eventActionId, setEventActionId] = useState<number | null>(null);

  async function summarizeEvent(eventId: number) {
    setEventActionId(eventId);
    setStatus("Summarizing event...");
    try {
      await summarizeEventById(eventId);
      await loadTimeline();
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("Event summary updated.");
    } catch {
      setStatus("Failed to summarize event.");
    } finally {
      setEventActionId(null);
    }
  }

  async function deepResearchEvent(eventId: number) {
    setEventActionId(eventId);
    setStatus("Researching event...");
    try {
      await researchEventById(eventId);
      await loadTimeline();
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("Event research updated.");
    } catch {
      setStatus("Failed to research event.");
    } finally {
      setEventActionId(null);
    }
  }

  async function acceptEventResearchSuggestion(eventId: number) {
    setEventActionId(eventId);
    setStatus("Applying event suggestion...");
    try {
      await applyEventResearchSuggestionById(eventId);
      await loadTimeline();
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("Event updated from suggestion.");
    } catch {
      setStatus("Failed to apply event suggestion.");
    } finally {
      setEventActionId(null);
    }
  }

  async function dismissEventResearchSuggestion(eventId: number) {
    setEventActionId(eventId);
    try {
      await dismissEventResearchSuggestionById(eventId);
      await loadTimeline();
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
    } catch {
      // ignore
    } finally {
      setEventActionId(null);
    }
  }

  return {
    eventActionId,
    summarizeEvent,
    deepResearchEvent,
    acceptEventResearchSuggestion,
    dismissEventResearchSuggestion,
  };
}
