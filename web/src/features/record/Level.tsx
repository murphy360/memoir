/** How loud the microphone hears you, as a bar and for screen readers as a meter. */
export function Level({
  level,
  label = "Input level",
}: {
  level: number;
  label?: string;
}) {
  const percent = Math.round(level * 100);
  return (
    <div
      className="level"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className="level-bar" style={{ width: `${percent}%` }} />
    </div>
  );
}
