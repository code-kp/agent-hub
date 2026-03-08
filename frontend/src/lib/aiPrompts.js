export function buildConversationTitleInstructions() {
  return [
    "Generate a concise conversation title for a chat workspace from the user's opening request.",
    "Return only the title text.",
    "Keep it specific, concrete, and professional.",
    "Use 3 to 7 words.",
    "Do not use quotes, markdown, emojis, or ending punctuation.",
    "Do not prefix with Title: or Conversation:.",
    "Focus on the user's main intent.",
  ].join("\n");
}

export function buildConversationTitleMessage(requestText) {
  return [
    "Create a concise title for this conversation from this opening user request:",
    String(requestText || "").trim(),
    "Return only the title.",
  ].join("\n");
}
