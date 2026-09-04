interface AutoMetaLogoProps {
  size?: number;
}


export function AutoMetaLogo({ size = 28 }: AutoMetaLogoProps) {
  return (
    <svg
      aria-label="AutoMeta"
      height={size}
      role="img"
      viewBox="0 0 28 28"
      width={size}
    >
      <rect fill="#16233F" height="26.8" rx="7.8" width="26.8" x="0.6" y="0.6" />
      <rect
        fill="none"
        height="26.8"
        rx="7.8"
        stroke="#000"
        strokeOpacity="0.2"
        width="26.8"
        x="0.6"
        y="0.6"
      />
      <g
        fill="none"
        stroke="#fff"
        strokeLinecap="round"
        strokeOpacity="0.46"
        strokeWidth="1.25"
      >
        <path d="M14 11.4V8.4" />
        <path d="M16.6 14h3" />
        <path d="M14 16.6v3" />
        <path d="M11.4 14h-3" />
      </g>
      <circle cx="14" cy="14" fill="#fff" r="3.15" />
      <circle cx="14" cy="6.75" fill="#6FE0C0" r="2.05" />
      <circle cx="21.25" cy="14" fill="#fff" fillOpacity="0.92" r="2.05" />
      <circle cx="14" cy="21.25" fill="#fff" fillOpacity="0.92" r="2.05" />
      <circle cx="6.75" cy="14" fill="#fff" fillOpacity="0.92" r="2.05" />
    </svg>
  );
}
