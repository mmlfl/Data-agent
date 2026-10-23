/** Data Agent's data-flow monogram, shared by the workspace and assistant. */
export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M7 5h8a11 11 0 0 1 0 22H7V5Z"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path
        d="m12 20 4-7 5 3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="20" r="1.8" fill="currentColor" />
      <circle cx="16" cy="13" r="1.8" fill="currentColor" />
      <circle cx="21" cy="16" r="1.8" fill="currentColor" />
    </svg>
  );
}
