/** Stand-ins for the browser's microphone, MediaRecorder and audio analysis. */

export class FakeRecorder {
  static isTypeSupported = (t: string) => t === "audio/webm;codecs=opus";
  static last: FakeRecorder | null = null;
  state: "inactive" | "recording" = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(_stream: unknown, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? "audio/webm";
    FakeRecorder.last = this;
  }

  start() {
    this.state = "recording";
    this.timer = setInterval(
      () => this.ondataavailable?.({ data: new Blob(["0123456789"]) }),
      20,
    );
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.ondataavailable?.({ data: new Blob(["last"]) });
    this.state = "inactive";
    setTimeout(() => this.onstop?.(), 0);
  }
}

export function installMedia(options: { deny?: boolean } = {}) {
  const track = { stop: vi.fn() };
  const getUserMedia = vi.fn(async () => {
    if (options.deny) throw new DOMException("no", "NotAllowedError");
    return { getTracks: () => [track] };
  });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia,
      enumerateDevices: vi.fn(async () => [
        { kind: "audioinput", deviceId: "mic-1", label: "Built-in microphone" },
      ]),
    },
  });
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  vi.stubGlobal(
    "AudioContext",
    class {
      createAnalyser() {
        return {
          fftSize: 32,
          getFloatTimeDomainData: (a: Float32Array) => a.fill(0.1),
        };
      }
      createMediaStreamSource() {
        return { connect: () => undefined };
      }
      resume() {
        return Promise.resolve();
      }
      close() {
        return Promise.resolve();
      }
    },
  );
  vi.stubGlobal("requestAnimationFrame", () => 1);
  vi.stubGlobal("cancelAnimationFrame", () => undefined);
  URL.createObjectURL = vi.fn(() => "blob:take");
  return { getUserMedia, track };
}
