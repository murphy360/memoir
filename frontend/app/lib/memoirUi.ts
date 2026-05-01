import { Question } from "../types";

export const AUDIO_DEVICE_STORAGE_KEY = "memoir:last-audio-device-id";

export const CLIPBOARD_IMAGE_EXTENSIONS: Record<string, string> = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/jpg": ".jpg",
  "image/gif": ".gif",
  "image/webp": ".webp",
};

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function normalizeQuestionText(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

export function dedupeQuestions(items: Question[]): Question[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = normalizeQuestionText(item.text);
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function displayPeriodSummary(summary: string): string {
  return summary
    .replace(/^Auto-generated summary:\s*/i, "")
    .replace(/^Auto-generated biography:\s*/i, "");
}
