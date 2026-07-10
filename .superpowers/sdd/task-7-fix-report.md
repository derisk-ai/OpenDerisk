# Task-7 Fix Report — C1: structured VIS rendering is a dead end

## The bug (C1)

`SceneAgentWorkspaceConverter` emits a markdown code fence:

````
```scene_agent_workspace
{"render_name":"scene_agent_workspace","planning":null,"execution":[...],"summary":...}
```
````

This string travels over SSE as `{ "vis": <fence_string> }`. In
`web/src/hooks/use-chat.ts`, because the scene-agent send does NOT set
`ext_info.incremental`, `isIncremental` is falsy → `message = parsedData.vis`
(the fence **string**) → `onMessage(message)` receives a **string**.

`web/src/app/workspaces/detail/use-scene-agent-chat.ts`'s `onMessage` only
handled `typeof message === 'object'`, so the string fell through →
`workspaceView` never updated → `AgentWorkspaceRenderer` only ever showed the
empty state. Structured VIS rendering was dead end-to-end.

## Fix (Option B — frontend only, localized)

Extracted a pure, side-effect-free helper
`parseSceneAgentWorkspaceString(s: unknown): Record<string, unknown> | null` in
a new sibling module:

- `web/src/app/workspaces/detail/parse-scene-agent-workspace-string.ts`

  - Matches ```` ```scene_agent_workspace\n{...}\n``` ```` via
    `/```scene_agent_workspace\n([\s\S]*?)\n```/` and `JSON.parse`s the captured
    body.
  - Falls back to `JSON.parse(message)` when the string is already bare JSON
    (starts with `{`); rejects non-object parses (arrays / primitives).
  - Returns `null` for non-strings, empty/whitespace strings, non-matching
    strings, and malformed JSON (never throws).

The hook imports + re-exports the helper:
`export { parseSceneAgentWorkspaceString } from './parse-scene-agent-workspace-string';`
in `use-scene-agent-chat.ts`.

### `onMessage` refactor (`use-scene-agent-chat.ts`)

The single `onMessage` block now branches on the message type:

```ts
onMessage: (message: unknown) => {
  const routeObject = (obj: object) => {
    const step = parseAgentSteps(obj);
    if (step) { appendStep(step); return; }
    const mv = obj as Record<string, unknown>;
    if (mv.render_name === 'scene_agent_workspace' || Array.isArray(mv.execution)) {
      setWorkspaceView((prev) => parseWorkspaceView(obj, prev));
    }
  };

  if (message && typeof message === 'object') {
    routeObject(message as object);
    return;
  }
  // scene-agent send leaves ext_info.incremental unset → use-chat forwards the
  // vis fence as a STRING. Extract the JSON body and route it the same way.
  if (typeof message === 'string') {
    const parsed = parseSceneAgentWorkspaceString(message);
    if (parsed) routeObject(parsed);
  }
},
```

Behavior for non-matching strings is unchanged (no-op). Object routing
(step-list first, then `scene_agent_workspace`) is unchanged.

### Why a sibling module (not inline)

Defining the helper inside `use-scene-agent-chat.ts` made the test import
`../use-scene-agent-chat`, which transitively pulls `use-chat.ts` →
`parse-vis.ts` → `remark-parse` (ESM-only). Jest's Node env (`ts-jest`, no ESM
preset) crashed with `SyntaxError: Unexpected token 'export'` before the test
ran. Moving the pure string helper to a sibling file keeps it free of that
ESM-only dependency and unit-testable in plain Node, matching the TDD brief.

## New test cases

Added to `web/src/app/workspaces/detail/__tests__/use-scene-agent-chat.test.ts`,
in a `describe('parseSceneAgentWorkspaceString', …)` block (8 cases):

1. Fenced `scene_agent_workspace` string → parsed object (matching body).
2. Bare JSON string (no fence) → parsed object (fallback).
3. Normal markdown `**hello**` → null.
4. Fenced string with malformed JSON body → null, no throw.
5. Non-string / empty / whitespace-only → null.
6. Execution payload preserved through a fence parse (round-trip).
7. Fence embedded in surrounding markdown still parsed (regex not anchored).
8. Bare JSON that parses to a non-object (array, quoted string) → null.

The helper is the covered unit; the hook wiring (onMessage actually invokes the
helper in its string branch) is verified by reading the refactored handler.

## Verification

### Jest — target file

```
$ npx jest src/app/workspaces/detail/__tests__/use-scene-agent-chat.test.ts
Test Suites: 1 passed, 1 total
Tests:       11 passed, 11 total
```

### Jest — full `detail/__tests__/` directory

```
$ npx jest src/app/workspaces/detail/__tests__/
Test Suites: 5 passed, 5 total
Tests:       43 passed, 43 total
```

(43 ≥ the 35+ bar from the brief; includes the 3 pre-existing
`buildSceneAgentSendData` tests, the 8 new helper tests, and 32 existing tests
across `parse-agent-steps`, `parse-workspace-view`, `agent-workspace-types`,
and `scene-agent-send-data`.)

### tsc

```
$ npx tsc --noEmit | grep -iE "scene-agent-workspace-string|use-scene-agent-chat"
NO ERRORS in changed files
```

`tsc --noEmit` reports only pre-existing errors in unrelated files
(`tab-streaming-config.tsx`, `agent-skills/detail/page.tsx`, etc.). No new
errors were introduced in any file touched by this fix
(`parse-scene-agent-workspace-string.ts`, `use-scene-agent-chat.ts`, the test).

## C1 status: resolved

The structured VIS fence string that `use-chat.ts` forwards to `onMessage` is
now parsed back into an object and routed through the existing
`parseWorkspaceView` path, so `AgentWorkspaceRenderer` receives real
planning/execution/summary data instead of lingering in the empty state.

## Files changed

- `web/src/app/workspaces/detail/parse-scene-agent-workspace-string.ts` (new, pure helper)
- `web/src/app/workspaces/detail/use-scene-agent-chat.ts` (import + re-export; `onMessage` refactored to handle string fences)
- `web/src/app/workspaces/detail/__tests__/use-scene-agent-chat.test.ts` (+8 helper test cases)