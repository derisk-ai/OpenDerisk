import { Button, Popover, Typography } from 'antd';
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
          // open={true}
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
