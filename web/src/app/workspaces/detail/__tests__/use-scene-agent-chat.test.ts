import { buildSceneAgentSendData, type SceneAgentSendPayload } from '../scene-agent-send-data';
import { parseSceneAgentWorkspaceString } from '../parse-scene-agent-workspace-string';

describe('buildSceneAgentSendData', () => {
  test('text + resources + model 构造多模态 user_input 与 chat_in_params', () => {
    const resources = [{ type: 'file_url', file_url: { url: 'u', file_name: 'f.txt' } }];
    const payload: SceneAgentSendPayload = { text: '你好', resources, model: 'gpt-4' };
    const data = buildSceneAgentSendData(payload, { workspaceId: 9, taskId: 3 }, 'c1');

    // user_input 多模态
    expect(data.user_input).toEqual({
      role: 'user',
      content: [...resources, { type: 'text', text: '你好' }],
    });
    // chat_in_params: resource + model
    expect(data.chat_in_params).toEqual([
      { param_type: 'resource', param_value: JSON.stringify(resources), sub_type: 'common_file' },
      { param_type: 'model', param_value: 'gpt-4' },
    ]);
    // model_name
    expect(data.model_name).toBe('gpt-4');
    // ext_info
    expect(data.ext_info).toMatchObject({ vis_render: 'scene_agent_workspace', workspace_id: 9, task_id: 3 });
  });

  test('playbookCommand 构造 playbook_command chat_in_params, user_input 为纯 topic 字符串', () => {
    const playbookCommand = { playbook_id: 7, playbook_name: '营收分析' };
    const payload: SceneAgentSendPayload = { text: '营收分析', playbookCommand };
    const data = buildSceneAgentSendData(payload, { workspaceId: 9 }, 'c1');

    // user_input 为纯字符串
    expect(data.user_input).toBe('营收分析');
    // chat_in_params 含 playbook_command
    expect(data.chat_in_params).toEqual([
      { param_type: 'playbook_command', sub_type: 'playbook', param_value: JSON.stringify(playbookCommand) },
    ]);
    // 无 model_name
    expect(data.model_name).toBeUndefined();
  });

  test('text-only: user_input 为纯字符串, 无 chat_in_params', () => {
    const payload: SceneAgentSendPayload = { text: '你好' };
    const data = buildSceneAgentSendData(payload, { workspaceId: 9 }, 'c1');

    expect(data.user_input).toBe('你好');
    expect(data.chat_in_params).toBeUndefined();
    expect(data.model_name).toBeUndefined();
    // ext_info 仍含 vis_render
    expect(data.ext_info).toMatchObject({ vis_render: 'scene_agent_workspace', workspace_id: 9 });
  });
});

describe('parseSceneAgentWorkspaceString', () => {
  test('fenced scene_agent_workspace string → parsed object', () => {
    const body = '{"render_name":"scene_agent_workspace","planning":null,"execution":[],"summary":null}';
    const fenced = '```scene_agent_workspace\n' + body + '\n```';
    const parsed = parseSceneAgentWorkspaceString(fenced);
    expect(parsed).toEqual({
      render_name: 'scene_agent_workspace',
      planning: null,
      execution: [],
      summary: null,
    });
  });

  test('bare JSON string (no fence) → parsed object (fallback)', () => {
    const s = '{"render_name":"scene_agent_workspace","execution":[]}';
    const parsed = parseSceneAgentWorkspaceString(s);
    expect(parsed).toEqual({ render_name: 'scene_agent_workspace', execution: [] });
  });

  test('normal markdown string → null', () => {
    expect(parseSceneAgentWorkspaceString('**hello**')).toBeNull();
  });

  test('fenced string with malformed JSON body → null (no throw)', () => {
    const fenced = '```scene_agent_workspace\n{not valid json\n```';
    expect(() => parseSceneAgentWorkspaceString(fenced)).not.toThrow();
    expect(parseSceneAgentWorkspaceString(fenced)).toBeNull();
  });

  test('non-string or empty → null', () => {
    expect(parseSceneAgentWorkspaceString(null as unknown as string)).toBeNull();
    expect(parseSceneAgentWorkspaceString(undefined as unknown as string)).toBeNull();
    expect(parseSceneAgentWorkspaceString(123 as unknown as string)).toBeNull();
    expect(parseSceneAgentWorkspaceString('')).toBeNull();
    expect(parseSceneAgentWorkspaceString('   ')).toBeNull();
  });

  test('execution payload is preserved through fence parse', () => {
    const obj = {
      render_name: 'scene_agent_workspace',
      planning: { goal: 'x' },
      execution: [{ id: 's1', title: 't', type: 'tool_call', status: 'done' }],
      summary: 'done',
    };
    const fenced = '```scene_agent_workspace\n' + JSON.stringify(obj) + '\n```';
    const parsed = parseSceneAgentWorkspaceString(fenced);
    expect(parsed).toEqual(obj);
  });

  test('fence embedded in surrounding markdown → still parsed (regex is not anchored)', () => {
    const body = '{"render_name":"scene_agent_workspace","execution":[]}';
    const md = 'some prefix\n```scene_agent_workspace\n' + body + '\n```\ntail';
    expect(parseSceneAgentWorkspaceString(md)).toEqual({
      render_name: 'scene_agent_workspace',
      execution: [],
    });
  });

  test('bare JSON that is not an object (e.g. array or number string) → null for non-object', () => {
    expect(parseSceneAgentWorkspaceString('[1,2,3]')).toBeNull();
    expect(parseSceneAgentWorkspaceString('"a string"')).toBeNull();
  });
});