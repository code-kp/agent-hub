function toValidDate(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const nextDate = value instanceof Date ? value : new Date(value);
  return Number.isNaN(nextDate.getTime()) ? null : nextDate;
}

export function formatTime(value, { withSeconds = false } = {}) {
  const date = toValidDate(value);
  if (!date) {
    return "";
  }

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
  });
}

export function toDateTimeAttr(value) {
  const date = toValidDate(value);
  return date ? date.toISOString() : undefined;
}

export function hasValidDate(value) {
  return Boolean(toValidDate(value));
}
