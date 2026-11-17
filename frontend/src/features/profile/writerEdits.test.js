import { test, expect } from "bun:test";
import {
  changedLineIndices,
  mergeWriterEdits,
  coveredTargetIndices,
} from "./writerEdits.js";
test("finds changed/new sentences without rewriting reordered or repeated originals", () => {
  expect(changedLineIndices(["B", "A", "C", "A"], ["A", "B", "A"])).toEqual([
    2,
  ]);
});
test("partial apply preserves unselected sentences exactly", () => {
  expect(
    mergeWriterEdits(
      ["Original 1", "rough 2", "Original 3"],
      [1],
      ["Polished 2"],
    ),
  ).toEqual(["Original 1", "Polished 2", "Original 3"]);
});
test("merged selected range, append and empty field preserve untouched text", () => {
  expect(mergeWriterEdits(["a", "b", "c", "d"], [1, 3], ["B/D"])).toEqual([
    "a",
    "B/D",
    "c",
  ]);
  expect(mergeWriterEdits(["a"], [0], ["a", "b"], "append")).toEqual([
    "a",
    "b",
  ]);
  expect(mergeWriterEdits([], [], ["b"])).toEqual(["b"]);
});

test("applying only one suggestion preserves all uncovered originals", () => {
  const lines = ["rough one", "rough two", "unchanged"];
  const covered = coveredTargetIndices(
    lines,
    [0, 1],
    [{ sources: ["rough two"] }],
  );
  expect(covered).toEqual([1]);
  expect(mergeWriterEdits(lines, covered, ["Polished two"])).toEqual([
    "rough one",
    "Polished two",
    "unchanged",
  ]);
});
