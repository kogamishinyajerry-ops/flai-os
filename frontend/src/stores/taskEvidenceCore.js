/** Pure projection for one bounded evidence preview response. */
export function projectEvidencePreview(preview) {
  if (preview?.truncated === true) {
    return { findings: [], refusals: [], truncated: true, error: "" };
  }
  if (preview?.isText !== true || typeof preview?.text !== "string") {
    return { findings: [], refusals: [], truncated: false, error: "preview_unavailable" };
  }
  try {
    const data = JSON.parse(preview.text);
    return {
      findings: Array.isArray(data?.findings) ? data.findings : [],
      refusals: Array.isArray(data?.refusals) ? data.refusals : [],
      truncated: false,
      error: "",
    };
  } catch {
    return { findings: [], refusals: [], truncated: false, error: "invalid_json" };
  }
}
