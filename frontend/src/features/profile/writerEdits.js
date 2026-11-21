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
  const sources = new Map();
  bullets.flatMap((b) => b.sources || []).forEach((source) => {
    const key = normalizeSourceLine(source);
    sources.set(key, (sources.get(key) || 0) + 1);
  });
  return targets.filter((index) => {
    const key = normalizeSourceLine(lines[index]);
    if (!sources.get(key)) return false;
    sources.set(key, sources.get(key) - 1);
    return true;
  });
}

export function normalizeSourceLine(text) {
  return text.normalize("NFC").trim().replace(/^(?:[•*]\s*|-\s+|\d+[.)]\s+)/, "");
}

export function groupWriterSuggestions(lines, targets, bullets) {
  const available = new Set(targets);
  return bullets.map((bullet, proposalIndex) => {
    const candidates = targets.filter((index) => available.has(index)
      && (!bullet.targetIndices || bullet.targetIndices.includes(index)));
    const indices = coveredTargetIndices(lines, candidates, [bullet]);
    indices.forEach((index) => available.delete(index));
    return { bullet, proposalIndex, indices, anchor: indices.length ? Math.min(...indices) : null };
  });
}

export function isChangedSuggestion(bullet) {
  if (bullet.change_kind === "editorial_quickfix") return true;
  if (bullet.replacement_lines?.length > 1) return true;
  const normalize = (text) => normalizeSourceLine(text).replace(/[.!。]+$/, "").trim();
  return normalize(bullet.text) !== normalize((bullet.sources || []).join("\n"));
}

export function applyWriterSuggestions(lines, targets, bullets, mode = "replace") {
  const groups = groupWriterSuggestions(lines, targets, bullets);
  const replacement = (b) => b.replacement_lines?.length ? b.replacement_lines : [b.text];
  if (mode === "append") return mergeWriterEdits(lines, [], bullets.flatMap(replacement), mode);
  const replaced = new Set(groups.flatMap((g) => g.indices));
  return [
    ...lines.flatMap((line, index) => {
      const anchored = groups.filter((g) => g.anchor === index);
      return anchored.length ? anchored.flatMap((g) => replacement(g.bullet)) : replaced.has(index) ? [] : [line];
    }),
    ...groups.filter((g) => g.anchor === null).flatMap((g) => replacement(g.bullet)),
  ];
}
