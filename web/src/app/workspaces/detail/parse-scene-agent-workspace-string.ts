/**
 * Parse a `scene_agent_workspace` vis fence (or a bare JSON object string) into
 * the structured object it carries. Returns null for non-matching / malformed
 * input so callers can no-op safely.
 *
 * The backend converter (`SceneAgentWorkspaceConverter`) emits a markdown code
 * fence of the form:
 *
 * ```scene_agent_workspace
 * {"render_name":"scene_agent_workspace","planning":null,"execution":[...],"summary":...}
 * ```
 *
 * which travels over SSE as `{ vis: <fence string> }`. Because the scene-agent
 * send does not set `ext_info.incremental`, `use-chat.ts` forwards the fence
 * STRING (not the parsed object) to `onMessage`, so we must extract the JSON
 * body here before routing it through the object path.
 *
 * Kept in a sibling module (rather than inside the hook file) so it can be unit
 * tested without pulling `use-chat.ts`'s ESM-only `remark-parse` dependency
 * into the Node test environment.
 */
const FENCE_RE = /```scene_agent_workspace\n([\s\S]*?)\n```/;

export function parseSceneAgentWorkspaceString(
  s: unknown,
): Record<string, unknown> | null {
  if (typeof s !== 'string' || !s) return null;
  const trimmed = s.trim();
  if (!trimmed) return null;

  // Fenced form.
  const match = FENCE_RE.exec(trimmed);
  if (match) {
    try {
      return JSON.parse(match[1]);
    } catch {
      return null;
    }
  }

  // Bare-JSON fallback (the string IS the object, no fence).
  if (trimmed.startsWith('{')) {
    try {
      const parsed = JSON.parse(trimmed);
      return parsed && typeof parsed === 'object'
        ? (parsed as Record<string, unknown>)
        : null;
    } catch {
      return null;
    }
  }

  return null;
}