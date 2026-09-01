/**
 * Shared scrubbing for the server-rendered anatomical muscle-map SVG.
 * - scope its `:root` custom-property block to `<svg>` so tokens (esp.
 *   `--surface`) can't leak into the app
 * - drop the server-baked title / subtitle / "most worked" caption lines —
 *   the card supplies its own header
 * - trim the padding those captions occupied
 * - optionally outline one muscle region (client-side selection highlight)
 */
export function scrubMuscleSvg(raw: string, activeMuscle?: string | null): string {
  let out = raw
    .replace(/:root\s*\{/g, "svg{")
    .replace(/<text\b[^>]*font-size="(?:3\.4|3\.2|3|2\.5|2\.4|2\.3)"[^>]*>[^<]*<\/text>/g, "")
    .replace(
      /viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"/,
      (_m, x, y, w, h) => `viewBox="${x} ${Number(y) + 9} ${w} ${Number(h) - 11}"`,
    )
    .replace(/<svg /, '<svg class="vf-mm-svg" ');

  if (activeMuscle && /^[a-z_]+$/.test(activeMuscle)) {
    out = out.replace(
      "</svg>",
      `<style>[data-muscle="${activeMuscle}"]{stroke:var(--accent);stroke-width:0.9;paint-order:stroke;}` +
      `[data-muscle]:not([data-muscle="${activeMuscle}"]){opacity:0.45;}</style></svg>`,
    );
  }
  return out;
}
