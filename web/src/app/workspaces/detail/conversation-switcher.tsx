'use client';

import { useState } from 'react';
import { Dropdown, Button, Modal, Input, message } from 'antd';
import { useRequest } from 'ahooks';
import {
  apiInterceptors,
  listConversations,
  setCurrentConversation,
  renameConversation,
  createConversation,
  linkConversation,
} from '@/client/api';

export interface ConversationSwitcherProps {
  workspaceId: number;
  currentConvUid: string;
  onChanged: (convUid: string) => void;
}

export function ConversationSwitcher({
  workspaceId,
  currentConvUid,
  onChanged,
}: ConversationSwitcherProps) {
  const [renameTarget, setRenameTarget] = useState<{ convUid: string; title: string } | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const { data: listRes, refresh } = useRequest(
    async () => apiInterceptors(listConversations({ workspace_id: workspaceId })),
    { refreshDeps: [workspaceId] },
  );
  const conversations = listRes?.[1] || [];

  const handleNew = async () => {
    const [, newConv] = await apiInterceptors(createConversation({ workspace_id: workspaceId }));
    if (!newConv?.conv_uid) return;
    await apiInterceptors(
      linkConversation({
        workspace_id: workspaceId,
        conv_uid: newConv.conv_uid,
        user_id: undefined,
      }),
    );
    await apiInterceptors(setCurrentConversation(workspaceId, newConv.conv_uid));
    refresh();
    onChanged(newConv.conv_uid);
    message.success('已新建会话');
  };

  const handleSelect = async (convUid: string) => {
    await apiInterceptors(setCurrentConversation(workspaceId, convUid));
    onChanged(convUid);
  };

  const handleRename = async () => {
    if (!renameTarget) return;
    await apiInterceptors(renameConversation(renameTarget.convUid, renameValue));
    setRenameTarget(null);
    refresh();
    message.success('已重命名');
  };

  const items = [
    ...conversations.map((c: any) => ({
      key: c.conv_uid,
      label: (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontWeight: c.conv_uid === currentConvUid ? 600 : 400,
          }}
        >
          <span>{c.title || c.conv_uid.slice(0, 8)}</span>
          <Button
            type="link"
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              setRenameTarget({ convUid: c.conv_uid, title: c.title || '' });
              setRenameValue(c.title || '');
            }}
          >
            重命名
          </Button>
        </div>
      ),
      onClick: () => handleSelect(c.conv_uid),
    })),
    { type: 'divider' as const },
    { key: '__new__', label: '+ 新建会话', onClick: handleNew },
  ];

  return (
    <>
      <Dropdown menu={{ items }} trigger={['click']}>
        <Button size="small">会话切换</Button>
      </Dropdown>
      <Modal
        title="重命名会话"
        open={!!renameTarget}
        onOk={handleRename}
        onCancel={() => setRenameTarget(null)}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          placeholder="输入新的会话标题"
        />
      </Modal>
    </>
  );
}
