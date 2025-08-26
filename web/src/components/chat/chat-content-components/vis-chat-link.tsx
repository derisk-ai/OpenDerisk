import { ChatContentContext } from '@/contexts';
import { Button } from 'antd';
import React, { useContext } from 'react';

interface VisChatLinkProps {
  children: any;
  msg: string;
}
const VisChatLink: React.FC<VisChatLinkProps> = ({ children, msg }) => {
  const { handleChat: webHandleChat } = useContext(ChatContentContext);
  return (
    <Button
      className='ml-1 inline text-xs'
      onClick={() => {
        webHandleChat?.(msg);
      }}
      type='dashed'
      size='small'
    >
      {children || '点击分析当前异常'}
    </Button>
  );
};

export default VisChatLink;
