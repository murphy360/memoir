import { useRef } from "react";

/**
 * Plays a fresh recording. Chrome writes recordings without their length, so the player
 * would show no duration and could not seek; asking for a far point once makes the
 * browser work the length out, then playback returns to the start.
 */
export function TakePlayer({ src }: { src: string }) {
  const fixing = useRef(false);
  return (
    <audio
      controls
      preload="metadata"
      src={src}
      onLoadedMetadata={(e) => {
        const audio = e.currentTarget;
        if (audio.duration === Infinity) {
          fixing.current = true;
          audio.currentTime = Number.MAX_SAFE_INTEGER;
        }
      }}
      onDurationChange={(e) => {
        const audio = e.currentTarget;
        if (fixing.current && Number.isFinite(audio.duration)) {
          fixing.current = false;
          audio.currentTime = 0;
        }
      }}
    />
  );
}
