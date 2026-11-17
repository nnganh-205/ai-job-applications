// Exact source lines stay untouched unless explicitly selected for rewriting.
export function changedLineIndices(lines, baseline) {
  const remaining = new Map();
  baseline.forEach((line) =>
    remaining.set(line, (remaining.get(line) || 0) + 1),
  );
  return lines.flatMap((line, index) => {
    if (remaining.get(line)) {
      remaining.set(line, remaining.get(line) - 1);
      return [];
    }
    return line.trim() ? [index] : [];
  });
}

export function mergeWriterEdits(lines, indices, proposals, mode = "replace") {
  if (mode === "append")
    return [...lines, ...proposals.filter((text) => !lines.includes(text))];
  const chosen = new Set(indices);
  if (!chosen.size) return [...lines, ...proposals];
  const first = Math.min(...indices);
  return lines.flatMap((line, index) =>
    index === first ? proposals : chosen.has(index) ? [] : [line],
  );
}

export function coveredTargetIndices(lines, targets, bullets) {
  const normalize = (text) => text.trim().replace(/^(?:[•*\-]|\d+[.)])\s*/, "");
  const sources = new Set(
    bullets.flatMap((b) => b.sources || []).map(normalize),
  );
  return targets.filter((index) => sources.has(normalize(lines[index])));
}
