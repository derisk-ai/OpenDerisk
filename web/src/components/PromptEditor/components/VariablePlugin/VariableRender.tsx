import { Button, Popover, Typography, Input, Divider } from 'antd';
import React, { useEffect, useState } from 'react';
import {
  CustomPluginContent,
  CustomPopoverWrapper,
  VariableRenderWrapper,
} from './style';

export const VariableRender = (props: any) => {
  const { data, handleClickChangeVariable } = props;
  // 初次进入的提示浮层
  const [initTipOpen, setInitTipOpen] = useState(false);
  const [testValue, setTestValue] = useState('');

  useEffect(() => {
    const taskAgentInitTipFlag = localStorage.getItem('taskAgentInitTipFlag');
    // 如果已经关闭提示，则不再显示
    if (taskAgentInitTipFlag !== 'true' && data?.isFirst) {
      setInitTipOpen(true);
    } else {
      setInitTipOpen(false);
    }
  }, []);

  return (
    <VariableRenderWrapper>
      <Popover
        content={
          // 第一个变量且初次进入展示
          <div className="init_popover_content">
            <div>{`鼠标悬停可查看参数取值逻辑，输入 { 可快速引用参数。`}</div>
            <Button
              onClick={() => {
                setInitTipOpen(false);
                localStorage.setItem('taskAgentInitTipFlag', 'true');
              }}
            >
              我知道了
            </Button>
          </div>
        }
        open={initTipOpen}
        placement="right"
        trigger="click"
        getPopupContainer={(node) => node}
      >
        <Popover
          placement="bottom"
          content={
            <CustomPopoverWrapper>
              <div className="custom_popover_content_name">
                <Typography.Text
                  ellipsis={{
                    tooltip: true,
                  }}
                >
                  {data?.name || ''}
                </Typography.Text>
                {!data?.readonly && (
                  <div
                    className="custom_popover_content_switch"
                    onClick={() => {
                      handleClickChangeVariable(data?.matchPos);
                    }}
                  >
                    切换
                  </div>
                )}
              </div>
              <div>
                {data?.description && (
                  <Typography.Text
                    className="custom_popover_content_desc"
                    ellipsis={{
                      tooltip: data?.description,
                    }}
                  >
                    {data?.description || ''}
                  </Typography.Text>
                )}
              </div>
              
              <Divider style={{ margin: '8px 0' }} />
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <Typography.Text type="secondary" style={{ fontSize: '12px' }}>
                  变量测试 / Value Preview
                </Typography.Text>
                <Input 
                    placeholder="输入测试值 / Input test value" 
                    size="small" 
                    value={testValue}
                    onChange={(e) => setTestValue(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                />
                {testValue && (
                    <div style={{ 
                        background: '#f5f5f5', 
                        padding: '6px', 
                        borderRadius: '4px', 
                        fontSize: '12px',
                        color: '#333',
                        wordBreak: 'break-all'
                    }}>
                        {testValue}
                    </div>
                )}
              </div>

            </CustomPopoverWrapper>
          }
        >
          <CustomPluginContent>
            <img
              style={{ width: '16px' }}
              src={
                '/icons/variable_blue.png'
              }
            />
            <span>{data?.renderName || data?.name}</span>
          </CustomPluginContent>
        </Popover>
      </Popover>
    </VariableRenderWrapper>
  );
};

export default VariableRender;
