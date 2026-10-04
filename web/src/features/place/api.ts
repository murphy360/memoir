import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";

export type Placement = components["schemas"]["MemoryPlacement"];
export type SavedTo = components["schemas"]["SavedToOut"];
export type Suggestion = components["schemas"]["SuggestionOut"];
export type PlaceIn = components["schemas"]["PlaceMemory"];

export const placementKey = (memoryId: number) =>
  ["placement", memoryId] as const;

export async function loadPlacement(memoryId: number): Promise<Placement> {
  return unwrap(
    await api.GET("/api/memories/{memory_id}/placement", {
      params: { path: { memory_id: memoryId } },
    }),
  );
}

export async function placeMemory(memoryId: number, body: PlaceIn) {
  return unwrap(
    await api.POST("/api/memories/{memory_id}/place", {
      params: { path: { memory_id: memoryId } },
      body,
    }),
  );
}

/** "1960s, Summer job": where the memory is, in the storyteller's words. */
export function describe(saved: SavedTo): string {
  return saved.period_title
    ? `${saved.period_title}, ${saved.event_title}`
    : saved.event_title;
}
