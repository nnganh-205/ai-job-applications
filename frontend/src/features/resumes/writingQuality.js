const linesOf = (e) =>
  [
    ...(e.description || []),
    ...(e.responsibilities || []),
    ...(e.contributions || []),
    ...(e.details || []),
  ].filter((x) => typeof x === "string" && x.trim());
export function writingQuality(entry = {}) {
  const lines = linesOf(entry),
    words = (t) => t.trim().split(/\s+/).length;
  const checks = [
    {
      id: "action",
      label: "Động từ mở đầu",
      bad: lines
        .map((t, i) =>
          /^(?:mình |tôi |em )?(?:đã )?(?:làm\b|có làm\b|worked\b|responsible for\b)/i.test(
            t.trim(),
          )
            ? i + 1
            : null,
        )
        .filter(Boolean),
      help: "Mở đầu bằng hành động đúng với công việc: xây dựng, phân tích, kiểm thử, hỗ trợ…",
    },
    {
      id: "pronoun",
      label: "Xưng hô cá nhân",
      bad: lines
        .map((t, i) =>
          /(?:^|\s)(mình|tôi|em|I|my)(?:\s|$)/i.test(t) ? i + 1 : null,
        )
        .filter(Boolean),
      help: "Dùng câu mô tả công việc, bỏ “mình”, “tôi” trong bản CV.",
    },
    {
      id: "punctuation",
      label: "Viết hoa & dấu câu",
      bad: lines
        .map((t, i) =>
          !/^\p{Lu}/u.test(t.trim()) || !/[.!?]$/.test(t.trim()) ? i + 1 : null,
        )
        .filter(Boolean),
      help: "Viết hoa đầu câu và thống nhất dấu chấm cuối mỗi bullet.",
    },
    {
      id: "length",
      label: "Độ gọn của bullet",
      bad: lines.map((t, i) => (words(t) > 38 ? i + 1 : null)).filter(Boolean),
      help: "Mỗi bullet một ý chính. Câu quá dài nên tách hoặc viết gọn.",
    },
    {
      id: "specific",
      label: "Diễn đạt cụ thể",
      bad: lines
        .map((t, i) =>
          /nhiều thứ|mọi thứ|rất tốt|xuất sắc|năng động|hardworking|go-getter/i.test(
            t,
          )
            ? i + 1
            : null,
        )
        .filter(Boolean),
      help: "Ưu tiên việc thực tế, công cụ và đầu ra thay cho tính từ chung chung.",
    },
  ].map((c) => ({
    ...c,
    status: !lines.length ? "empty" : c.bad.length ? "warning" : "pass",
  }));
  const passed = checks.filter((c) => c.status === "pass").length;
  return {
    lines,
    checks,
    score: lines.length ? Math.round((passed / checks.length) * 100) : 0,
    passed,
    total: checks.length,
    hasMetric: lines.some((t) =>
      /\d+(?:[.,]\d+)?\s*(?:%|người|mẫu|giây|phút|bản|API|endpoint|khách)/i.test(
        t,
      ),
    ),
  };
}
export function entryTitle(entry, section, index) {
  return (
    entry.project_name ||
    entry.job_title ||
    entry.institution ||
    entry.activity_name ||
    entry.group ||
    `${{ project: "Dự án", experience: "Kinh nghiệm", education: "Học vấn", involvement: "Hoạt động", skills: "Nhóm kỹ năng" }[section] || "Thông tin"} ${index + 1}`
  );
}

export function quickEditorialEdits(entry, issue) {
  if (!["punctuation", "pronoun"].includes(issue)) return [];
  const edits = [];
  for (const field of [
    "description",
    "responsibilities",
    "contributions",
    "details",
  ]) {
    const original = entry[field];
    if (!Array.isArray(original)) continue;
    const proposed = original.map((line) => {
      let text = line.trim();
      if (issue === "pronoun")
        text = text.replace(/^(?:mình|tôi|em)\s+(?:đã\s+)?/i, "");
      if (text) text = text[0].toUpperCase() + text.slice(1);
      if (
        issue === "punctuation" &&
        text &&
        !/[.!?]$/.test(text) &&
        !/^https?:\/\//i.test(text)
      )
        text += ".";
      return text;
    });
    if (JSON.stringify(original) !== JSON.stringify(proposed))
      edits.push({ field, original, proposed });
  }
  return edits;
}
