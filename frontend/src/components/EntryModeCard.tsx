import type { ReviewEntryMode } from "../api/types";


interface EntryModeCardProps {
  description: string;
  label: string;
  mode: ReviewEntryMode;
  selected: boolean;
  onSelect: (mode: ReviewEntryMode) => void;
}


export function EntryModeCard({
  description,
  label,
  mode,
  selected,
  onSelect,
}: EntryModeCardProps) {
  return (
    <label className={`entry-mode-card entry-mode-card--${mode}${selected ? " is-selected" : ""}`}>
      <input
        checked={selected}
        name="entry-mode"
        onChange={() => onSelect(mode)}
        type="radio"
        value={mode}
      />
      <span className="entry-mode-card__copy">
        <strong>{label}</strong>
        <span>{description}</span>
      </span>
      <span aria-hidden="true" className="entry-mode-card__mark">
        {selected ? "●" : "○"}
      </span>
    </label>
  );
}
