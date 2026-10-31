"use strict";

const knowledge = [
  ...require("./knowledge.js"),
  ...require("./human_topics.js"),
];

function normalize(text) {
  return String(text || "")
    .normalize("NFKC")
    .toLocaleLowerCase()
    .match(/[\p{L}\p{N}]+/gu) || [];
}

/** Search the bundled starter notes by exact word overlap. */
function searchKnowledge(query, limit = 5) {
  const queryWords = new Set(normalize(query));
  if (queryWords.size === 0) return [];

  const safeLimit = Math.max(1, Math.min(Number(limit) || 5, 20));
  return knowledge
    .map((entry) => {
      const haystack = normalize(
        [entry.topic, ...entry.tags, entry.text].join(" ")
      );
      const score = haystack.reduce(
        (total, word) => total + (queryWords.has(word) ? 1 : 0),
        0
      );
      return { ...entry, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score || left.topic.localeCompare(right.topic))
    .slice(0, safeLimit);
}

module.exports = { knowledge, searchKnowledge };
