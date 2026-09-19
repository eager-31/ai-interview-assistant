const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export const formatDate = (iso) => dateTime.format(new Date(iso));

export function formatDuration(startIso, endIso) {
  const minutes = Math.round((new Date(endIso) - new Date(startIso)) / 60000);
  return minutes < 1 ? "under a minute" : `${minutes} min`;
}

export function formatClock(totalSeconds) {
  const seconds = Math.floor(totalSeconds);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

const SCORE_WORDS = { 1: "Needs work", 2: "Developing", 3: "Solid", 4: "Strong", 5: "Excellent" };
export const scoreWord = (score) => SCORE_WORDS[Math.round(score)] ?? "";

export const formatScore = (value) => (value == null ? "n/a" : Number.isInteger(value) ? String(value) : value.toFixed(1));
