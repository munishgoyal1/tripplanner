interface Props {
  message: string | null;
  onDismiss: () => void;
}

export default function ErrorBanner({ message, onDismiss }: Props) {
  if (!message) return null;

  return (
    <div role="alert" className="fixed left-1/2 top-3 z-[70] flex max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-3 rounded-xl bg-rose-50 px-4 py-2 text-sm text-rose-800 shadow-pop ring-1 ring-rose-200">
      <span>{message}</span>
      <button type="button" onClick={onDismiss} className="font-semibold" aria-label="Dismiss error">
        x
      </button>
    </div>
  );
}