import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState =
  "idle" | "starting" | "recording" | "stopped" | "error";

export type Take = { blob: Blob; seconds: number; url: string };

/** The formats browsers record in, best first (Chrome and Firefox: WebM; Safari: MP4). */
const TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

function bestType(): string | undefined {
  return TYPES.find((t) => window.MediaRecorder?.isTypeSupported?.(t));
}

/** A level from 0 to 1, read from the microphone many times a second. */
function meter(
  stream: MediaStream,
  onLevel: (level: number) => void,
): () => void {
  const Context =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext: typeof AudioContext })
      .webkitAudioContext;
  if (!Context) return () => undefined;
  const audio = new Context();
  const analyser = audio.createAnalyser();
  analyser.fftSize = 1024;
  audio.createMediaStreamSource(stream).connect(analyser);
  const samples = new Float32Array(analyser.fftSize);
  let frame = 0;
  const tick = () => {
    analyser.getFloatTimeDomainData(samples);
    let sum = 0;
    for (const s of samples) sum += s * s;
    onLevel(Math.min(1, Math.sqrt(sum / samples.length) * 4));
    frame = requestAnimationFrame(tick);
  };
  void audio.resume?.();
  tick();
  return () => {
    cancelAnimationFrame(frame);
    void audio.close();
  };
}

/** Open the microphone (a chosen device, or the default) and report its level. */
export function useMicrophone() {
  return useCallback(async (deviceId?: string) => {
    const audio: MediaTrackConstraints | boolean = deviceId
      ? { deviceId: { exact: deviceId } }
      : true;
    try {
      return await navigator.mediaDevices.getUserMedia({ audio });
    } catch (error) {
      // A remembered device may be gone (unplugged headset): fall back to the default.
      if (deviceId) return navigator.mediaDevices.getUserMedia({ audio: true });
      throw error;
    }
  }, []);
}

/**
 * Recording, as a small state machine: idle, starting (asking for the microphone),
 * recording (with elapsed time and level), stopped (a take to keep), or error.
 */
export function useRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [take, setTake] = useState<Take | null>(null);
  const open = useMicrophone();
  const parts = useRef<Blob[]>([]);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const stopMeter = useRef<() => void>(() => undefined);
  const started = useRef(0);
  const clock = useRef<ReturnType<typeof setInterval> | null>(null);

  const release = useCallback(() => {
    stopMeter.current();
    if (clock.current) clearInterval(clock.current);
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    setLevel(0);
  }, []);

  useEffect(() => release, [release]);

  const start = useCallback(
    async (deviceId?: string) => {
      setError(null);
      setTake(null);
      setState("starting");
      try {
        stream.current = await open(deviceId);
        const type = bestType();
        const rec = new MediaRecorder(
          stream.current,
          type ? { mimeType: type } : undefined,
        );
        parts.current = [];
        rec.ondataavailable = (e) => {
          if (e.data.size) parts.current.push(e.data);
        };
        recorder.current = rec;
        rec.start(1000);
        started.current = Date.now();
        setSeconds(0);
        clock.current = setInterval(
          () => setSeconds((Date.now() - started.current) / 1000),
          250,
        );
        stopMeter.current = meter(stream.current, setLevel);
        setState("recording");
      } catch (e) {
        release();
        setError(
          e instanceof DOMException && e.name === "NotAllowedError"
            ? "Memoir needs your permission to use the microphone."
            : "The microphone could not be opened.",
        );
        setState("error");
      }
    },
    [open, release],
  );

  /** Stop and keep the take. Resolves once the last piece is in. */
  const stop = useCallback(
    () =>
      new Promise<Take | null>((resolve) => {
        const rec = recorder.current;
        if (!rec || rec.state === "inactive") return resolve(null);
        const elapsed = (Date.now() - started.current) / 1000;
        rec.onstop = () => {
          const blob = new Blob(parts.current, {
            type: rec.mimeType || "audio/webm",
          });
          const kept = {
            blob,
            seconds: elapsed,
            url: URL.createObjectURL(blob),
          };
          release();
          setSeconds(elapsed);
          setTake(kept);
          setState("stopped");
          resolve(kept);
        };
        rec.stop();
      }),
    [release],
  );

  /** Stop and keep nothing. */
  const cancel = useCallback(() => {
    const rec = recorder.current;
    if (rec && rec.state !== "inactive") {
      rec.onstop = null;
      rec.stop();
    }
    parts.current = [];
    release();
    setTake(null);
    setSeconds(0);
    setState("idle");
  }, [release]);

  return { state, seconds, level, error, take, start, stop, cancel };
}
