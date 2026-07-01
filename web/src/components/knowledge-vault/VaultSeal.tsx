export default function VaultSeal({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="12" cy="11" r="4.5" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="12" cy="11" r="1.4" fill="currentColor" />
      <rect x="11.3" y="11.8" width="1.4" height="4.2" fill="currentColor" />
    </svg>
  );
}
