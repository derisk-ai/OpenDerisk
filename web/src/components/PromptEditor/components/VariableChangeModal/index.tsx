import React, { useEffect } from 'react';
// import { Highlight } from ';
import { CheckCircleFilled } from '@ant-design/icons';
import { Button, Collapse, CollapseProps, Flex, Typography } from 'antd';
import { VariableChangeModalWrapper } from './style';

interface IProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  handleChangeVar: (params: {
    arg: string;
    name: string;
    mentionType: string;
  }) => void;
  variableList: any[];
  changeVarInfo?: any;
}

/**
 * 指令切换弹窗
 */
const VariableChangeModal = (props: IProps) => {
  const { open, setOpen, variableList, handleChangeVar, changeVarInfo } = props;

  const [renderList, setRenderList] = React.useState<any[]>([]);

  const getExtra = (item: { arg: string; name: string }) => {
    if (item?.name === changeVarInfo?.name)
      return <CheckCircleFilled style={{ color: '#52c41a' }} />;
    return (
      <Button
        type="primary"
        className="hover-button"
        onClick={(e) => {
          e.stopPropagation();
          e.preventDefault();
          // setOpen(false);
          handleChangeVar({ ...item, mentionType: 'variable' });
        }}
      >
        切换
      </Button>
    );
  };

  const items: CollapseProps['items'] = renderList?.map((item) => ({
    key: item.name,
    label: (
      <Flex justify="space-between" align="center" gap={4}>
        <Flex align="center" gap={4} style={{ flex: 1, overflowX: 'hidden' }}>
          <div>{item?.arg}</div>
          <Typography.Text
            ellipsis={{ tooltip: item?.description }}
            className="descriptions"
          >
            # {item?.description}
          </Typography.Text>
        </Flex>
        {getExtra(item)}
      </Flex>
    ),
    children: (
      <div className="content">
        {/* <VariableCode value={item.content} readonly={true} /> */}
        {item?.script}
        {/* <Highlight copyable={false}>{item?.script}</Highlight> */}
      </div>
    ),
  }));

  useEffect(() => {
    if (changeVarInfo?.arg) {
      const { arg } = changeVarInfo;
      // 根据arg筛选出对应的变量
      setRenderList(variableList.filter((item) => item.arg === arg));
    } else {
      setRenderList(variableList);
    }
  }, [changeVarInfo, variableList]);

  return (
    <VariableChangeModalWrapper
      title="切换变量"
      open={open}
      onCancel={() => setOpen(false)}
      // maskClosable={false}
      footer={null}
    >
      <Collapse bordered={false} items={items} />
    </VariableChangeModalWrapper>
  );
};

export default VariableChangeModal;
