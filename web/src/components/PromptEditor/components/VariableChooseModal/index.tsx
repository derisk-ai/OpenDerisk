import { useEffect, useRef, useState } from 'react';
// import { Highlight } from '@alipay/tech-ui';
import { Rect } from '@codemirror/view';
import { Empty, Flex, Popover, Typography } from 'antd';
import React from 'react';
import { VariableChooseModalStyle } from './style';

interface IVariableChooseModalProps {
  cursorPosition: Rect | null;
  getPopPosition: any;
  variableMatchContent: any;
  variableList: any;
  setOpen: (val: boolean) => void;
  handleChangeVar: (params: { arg: string; name: string }) => void;
}

const VariableChooseModal = (props: IVariableChooseModalProps) => {
  const {
    cursorPosition,
    getPopPosition,
    setOpen,
    variableList,
    variableMatchContent,
    handleChangeVar,
  } = props;

  const popRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number }>();
  const [renderVariableList, setRenderVariableList] = useState<any>([]);

  const updatePosition = () => {
    const pos = getPopPosition?.(popRef, cursorPosition);
    if (pos) {
      setPosition(pos);
    }
  };
  /**
   * 根据匹配内容检索列表
   */
  const handleSearch = (val: string) => {
    // 输入内容带有{{}}需要去除后进行匹配
    const curVal = val?.replace(/{{|}}/g, '');
    const filterList =
      variableList?.filter((item: any) => item?.arg?.includes(curVal)) || [];
    setRenderVariableList(filterList);
  };

  // 监听浮窗高度变化
  useEffect(() => {
    if (popRef.current) {
      const resizeObserver = new ResizeObserver(() => {
        updatePosition(); // 高度变化时重新计算位置
      });
      resizeObserver.observe(popRef.current);
      // 清理监听器
      return () => {
        resizeObserver.disconnect();
      };
    }
  }, []);

  useEffect(() => {
    handleSearch(variableMatchContent);
  }, [variableMatchContent]);

  useEffect(() => {
    setRenderVariableList(variableList || []);
  }, [variableList]);

  return (
    <VariableChooseModalStyle
      className="custom-command-modal"
      ref={popRef}
      hidden={!position}
      $position={position}
    >
      <div className="variable_choose_wrapper">
        {renderVariableList?.length ? (
          <>
            {renderVariableList?.map((item: any) => {
              return (
                <div
                  key={item.id}
                  className=""
                  onClick={() => {
                    // 替换变量，拼接为指定格式
                    handleChangeVar(item);
                    // 关闭浮层
                    setOpen(false);
                  }}
                >
                  <Flex
                    justify="space-between"
                    align="center"
                    className="variable_choose_item"
                    gap={4}
                  >
                    <Typography.Paragraph
                      ellipsis={{ tooltip: item.description }}
                    >
                      <span className="variable_choose_item_title">
                        {item.arg}
                      </span>
                      <span className="variable_choose_item_desc">
                        {' '}
                        # {item.description}
                      </span>
                    </Typography.Paragraph>
                    <Popover
                     // @ts-ignore
                      getPopupContainer={() => {
                        const container =
                          document?.querySelector('custom-choose');
                        return container;
                      }}
                      content={
                        <div
                          style={{
                            maxHeight: '260px',
                            width: '356px',
                            overflow: 'auto',
                          }}
                          className="custom-choose-modal"
                          onClick={(e) => {
                            e.stopPropagation();
                          }}
                        >
                          {item?.script}
                          {/* <Highlight copyable={false}>{item?.script}</Highlight> */}
                        </div>
                      }
                    >
                      <div
                        className="variable_choose_item_action"
                        onClick={(e) => {
                          e.stopPropagation();
                        }}
                      >
                        查看代码
                      </div>
                    </Popover>
                  </Flex>
                </div>
              );
            })}
          </>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </div>
    </VariableChooseModalStyle>
  );
};

export default React.memo(VariableChooseModal);
