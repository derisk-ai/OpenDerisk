import { buildSceneAgentSendData, type SceneAgentSendPayload } from '../scene-agent-send-data';

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