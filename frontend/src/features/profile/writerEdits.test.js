import { test, expect } from "bun:test";
import {
  changedLineIndices,
  mergeWriterEdits,
  coveredTargetIndices,
  groupWriterSuggestions,
  applyWriterSuggestions,
  isChangedSuggestion,
} from "./writerEdits.js";
test("finds changed/new sentences without rewriting reordered or repeated originals", () => {
  expect(changedLineIndices(["B", "A", "C", "A"], ["A", "B", "A"])).toEqual([
    2,
  ]);
});

test("suggestions appear beneath their own source and partial apply keeps source order", () => {
  const lines = ["rough A", "keep B", "rough C", "keep D"];
  const bullets = [{text: "A improved", sources: ["rough A"]}, {text: "C improved", sources: ["rough C"]}];
  expect(groupWriterSuggestions(lines, [0, 2], bullets).map((g) => g.anchor)).toEqual([0, 2]);
  expect(applyWriterSuggestions(lines, [0, 2], bullets)).toEqual(["A improved", "keep B", "C improved", "keep D"]);
  expect(applyWriterSuggestions(lines, [0, 2], [bullets[1]])).toEqual(["rough A", "keep B", "C improved", "keep D"]);
});

test("unchanged output is not presented as an improvement", () => {
  expect(isChangedSuggestion({text: "Already clear.", sources: ["Already clear"]})).toBe(false);
  expect(isChangedSuggestion({text: "Hỗ trợ kiểm thử.", sources: ["mình hỗ trợ kiểm thử"]})).toBe(true);
  expect(isChangedSuggestion({text: "Already clear.", sources: ["Already clear"], change_kind: "editorial_quickfix"})).toBe(true);
});

test("a split applies atomically at its source and preserves unrelated and duplicate lines", () => {
  const split = {text:'First task.\nSecond task.',replacement_lines:['First task.','Second task.'],sources:['long original']};
  expect(isChangedSuggestion(split)).toBe(true);
  expect(groupWriterSuggestions(['long original','keep','long original'],[0,2],[split])[0].anchor).toBe(0);
  expect(applyWriterSuggestions(['long original','keep','long original'],[0,2],[split]))
    .toEqual(['First task.','Second task.','keep','long original']);
  expect(applyWriterSuggestions(['keep','long original','last'],[1],[split]))
    .toEqual(['keep','First task.','Second task.','last']);
});

test("applying one duplicate source preserves the other occurrence and signed numbers", () => {
  const bullet = {text: "Improved source", sources: ["same source"]};
  expect(applyWriterSuggestions(["same source", "keep", "same source"], [0, 2], [bullet]))
    .toEqual(["Improved source", "keep", "same source"]);
  expect(coveredTargetIndices(["-3 °C", "3 °C"], [0, 1], [{sources: ["-3 °C"]}])).toEqual([0]);
  const duplicates = [{text: "First edit", sources: ["same"]}, {text: "Second edit", sources: ["same"]}];
  const groups = groupWriterSuggestions(["same", "keep", "same"], [0, 2], duplicates);
  expect(groups.map((g) => g.anchor)).toEqual([0, 2]);
  expect(applyWriterSuggestions(["same", "keep", "same"], [0, 2],
    [{...duplicates[1], targetIndices: groups[1].indices}])).toEqual(["same", "keep", "Second edit"]);
});

test("merged and supplemental facts preserve unrelated content", () => {
  const bullets = [{text: "Merged", sources: ["first", "third"]}, {text: "Additional", sources: ["new fact"]}];
  expect(applyWriterSuggestions(["first", "keep", "third", "last"], [0, 2], bullets))
    .toEqual(["Merged", "keep", "last", "Additional"]);
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
