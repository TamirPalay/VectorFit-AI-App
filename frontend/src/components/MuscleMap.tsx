import { useQuery } from "@tanstack/react-query";
import { API_BASE } from "../lib/api";
import { Segmented, Spinner } from "./ui/primitives";
import s from "./MuscleMap.module.css";

type View = "both" | "front" | "back";

interface Props {
  userId: number;
  from?: string;
  to?: string;
  view: View;
  onView: (v: View) => void;
}

/**
 * Fetches the server-rendered anatomical SVG and inlines it — scoping its
 * `:root` custom-property block to the <svg> element so it can't leak tokens
 * (notably `--surface`) into the app. Keeps the SVG's hover <title> tooltips
 * and its own light/dark `@media` handling.
 */
export function MuscleMap({ userId, from, to, view, onView }: Props) {
  const q = useQuery({
    queryKey: ["muscle-map-svg", userId, view, from, to],
    staleTime: 120_000,
    queryFn: async () => {
      const p = new URLSearchParams({ view, format: "svg", theme: "auto" });
      if (from) p.set("date_from", from);
      if (to) p.set("date_to", to);
      const res = await fetch(`${API_BASE}/users/${userId}/dashboard/muscle-map?${p}`);
      if (!res.ok) throw new Error("Couldn't load the muscle map");
      const raw = await res.text();
      return raw
        .replace(/:root\s*\{/g, "svg{")
        // drop the server-baked title / subtitle / captions / "most worked"
        // line — the card supplies its own header, toggle, and summary. Keep
        // only the low→peak gradient legend.
        .replace(/<text\b[^>]*font-size="(?:3\.4|3\.2|3|2\.5|2\.4|2\.3)"[^>]*>[^<]*<\/text>/g, "")
        // reclaim padding that held the removed title (top) + most-worked (bottom)
        .replace(
          /viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"/,
          (_m, x, y, w, h) => `viewBox="${x} ${Number(y) + 9} ${w} ${Number(h) - 11}"`,
        )
        .replace(/<svg /, '<svg class="vf-mm-svg" ');
    },
  });

  return (
    <div className={s.wrap}>
      <div className={s.toolbar}>
        <Segmented<View>
          value={view}
          onChange={onView}
          options={[
            { value: "both", label: "Both" },
            { value: "front", label: "Front" },
            { value: "back", label: "Back" },
          ]}
        />
      </div>
      <div className={s.stage}>
        {q.isLoading && <div className={s.loading}><Spinner /></div>}
        {q.isError && <p className="dim" style={{ padding: 24, fontSize: "0.85rem" }}>Muscle map unavailable.</p>}
        {q.data && <div className={s.svgHost} dangerouslySetInnerHTML={{ __html: q.data }} />}
      </div>
    </div>
  );
}
