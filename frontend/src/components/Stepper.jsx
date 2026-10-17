const STEPS = [
  { id: "setup", label: "Set up" },
  { id: "live", label: "Live" },
  { id: "report", label: "Report" },
];

export default function Stepper({ stage }) {
  const current = STEPS.findIndex((s) => s.id === stage);
  return (
    <ol className="stepper" aria-label="Progress">
      {STEPS.map((s, i) => (
        <li
          key={s.id}
          className={i === current ? "on" : i < current ? "done" : ""}
          aria-current={i === current ? "step" : undefined}
        >
          <span className="num">{i < current ? "✓" : i + 1}</span>
          {s.label}
        </li>
      ))}
    </ol>
  );
}
