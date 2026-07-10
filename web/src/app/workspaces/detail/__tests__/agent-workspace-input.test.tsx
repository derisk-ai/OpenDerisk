/** @jest-environment jsdom */
import { render, fireEvent, screen } from '@testing-library/react';
import { AgentWorkspaceInput } from '../agent-workspace-input';

jest.mock('@/client/api', () => ({
  apiInterceptors: jest.fn(() => Promise.resolve([null, []])),
  getModelList: jest.fn(),
  postChatModeParamsFileLoad: jest.fn(),
}));
jest.mock('ahooks', () => ({ useRequest: () => ({ loading: false }) }));

describe('AgentWorkspaceInput', () => {
  test('输入 / 且有 playbooks 时显示剧本列表', () => {
    const onSend = jest.fn();
    render(
      <AgentWorkspaceInput
        convUid="c1"
        onSend={onSend}
        playbooks={[{ playbook_id: 1, playbook_name: '营收分析' }]}
      />,
    );
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '/' } });
    expect(screen.getByText('营收分析')).toBeInTheDocument();
  });

  test('选中剧本后 onSend 携带 playbookCommand 与主题文本', () => {
    const onSend = jest.fn();
    render(
      <AgentWorkspaceInput
        convUid="c1"
        onSend={onSend}
        playbooks={[{ playbook_id: 1, playbook_name: '营收分析' }]}
      />,
    );
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '本月营收/' } });
    fireEvent.click(screen.getByText('营收分析'));
    expect(onSend).toHaveBeenCalledWith(
      expect.objectContaining({
        text: '本月营收',
        playbookCommand: { playbook_id: 1, playbook_name: '营收分析' },
      }),
    );
  });
});