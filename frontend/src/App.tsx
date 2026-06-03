import { useCallback, useEffect, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import TripPanel from "./components/TripPanel";
import { fetchTripView, selectItem, deselectItem } from "./api";
import type { TripView } from "./types";

export default function App() {
  const [view, setView] = useState<TripView | null>(null);
  const [loading, setLoading] = useState(true);
  const [focus, setFocus] = useState<{ kind: string; name: string } | null>(null);

  const refresh = useCallback(
    async (f: { kind: string; name: string } | null = focus) => {
      setLoading(true);
      try {
        setView(await fetchTripView(f ?? undefined));
      } finally {
        setLoading(false);
      }
    },
    [focus]
  );

  useEffect(() => {
    refresh(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFocus = async (kind: string, name: string) => {
    const f = { kind, name };
    setFocus(f);
    await refresh(f);
  };

  const handleClearFocus = async () => {
    setFocus(null);
    await refresh(null);
  };

  const handleSelect = async (kind: string, name: string) => {
    const next = await selectItem(kind, name);
    // selectItem returns the whole-trip view; if the user is currently zoomed
    // into one item, re-fetch the focused view so the panel doesn't jump back.
    setView(focus ? await fetchTripView(focus) : next);
  };

  const handleDeselect = async (kind: string, name: string) => {
    const next = await deselectItem(kind, name);
    setView(focus ? await fetchTripView(focus) : next);
  };

  return (
    <div className="flex h-screen">
      <section className="flex w-full flex-col md:w-1/2 lg:w-3/5">
        <ChatPanel onTurnComplete={() => refresh()} />
      </section>
      <aside className="hidden border-l md:block md:w-1/2 lg:w-2/5">
        <TripPanel
          view={view}
          loading={loading}
          onFocus={handleFocus}
          onClearFocus={handleClearFocus}
          onSelect={handleSelect}
          onDeselect={handleDeselect}
        />
      </aside>
    </div>
  );
}
