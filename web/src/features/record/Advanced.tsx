import { useEffect, useRef, useState } from "react";

import { Button } from "../../components/Button";
import { useStoredState } from "../../lib/storedState";
import { Level } from "./Level";
import { useMicrophone } from "./useRecorder";

export const DEVICE_KEY = "audio-device";

/** The microphone choice and a test, folded away: the storyteller never needs them. */
export function Advanced() {
  const [device, setDevice] = useStoredState<string>(DEVICE_KEY, "");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [testing, setTesting] = useState(false);
  const [level, setLevel] = useState(0);
  const open = useMicrophone();
  const stop = useRef<() => void>(() => undefined);

  async function list() {
    const all = await navigator.mediaDevices?.enumerateDevices?.();
    setDevices((all ?? []).filter((d) => d.kind === "audioinput"));
  }

  // Stop a running test when the panel goes away.
  useEffect(() => () => stop.current(), []);

  async function test() {
    if (testing) {
      stop.current();
      setTesting(false);
      return;
    }
    const stream = await open(device || undefined);
    await list();
    const audio = new AudioContext();
    const analyser = audio.createAnalyser();
    audio.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    let frame = 0;
    const tick = () => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const s of samples) sum += s * s;
      setLevel(Math.min(1, Math.sqrt(sum / samples.length) * 4));
      frame = requestAnimationFrame(tick);
    };
    tick();
    stop.current = () => {
      cancelAnimationFrame(frame);
      stream.getTracks().forEach((t) => t.stop());
      void audio.close();
      setLevel(0);
    };
    setTesting(true);
  }

  return (
    <details
      className="advanced"
      onToggle={(e) => {
        // Names of microphones are only known once the page may use one; list them on open.
        if (e.currentTarget.open) void list();
      }}
    >
      <summary>Advanced</summary>
      <label className="field">
        Microphone
        <select value={device} onChange={(e) => setDevice(e.target.value)}>
          <option value="">The usual one</option>
          {devices.map((d, i) => (
            <option key={d.deviceId || i} value={d.deviceId}>
              {d.label || `Microphone ${i + 1}`}
            </option>
          ))}
        </select>
      </label>
      <Button onClick={() => void test()}>
        {testing ? "Stop the test" : "Test the microphone"}
      </Button>
      {testing ? <Level level={level} label="Test level" /> : null}
      <p className="hint">The choice is remembered on this device.</p>
    </details>
  );
}
