import axe from "axe-core";

// jsdom has no canvas. axe copes with a missing 2D context (it uses one to
// spot icon-font ligatures); this only keeps jsdom from logging "Not
// implemented" on every run.
HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext;

/**
 * axe-core's critical and serious violations inside `node`, as readable
 * lines (empty when clean). Colour contrast is skipped: jsdom lays nothing
 * out, so it cannot be measured here.
 */
export async function axeViolations(node: Element = document.body): Promise<string[]> {
  const results = await axe.run(node, {
    rules: { "color-contrast": { enabled: false } },
    resultTypes: ["violations"],
  });
  return results.violations
    .filter((violation) => violation.impact === "critical" || violation.impact === "serious")
    .map((violation) => `${violation.id}: ${violation.help} — ${violation.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}
