import { Empty, Tree, Divider } from 'antd';
import React, { useState } from 'react';
import { UpOutlined, DownOutlined } from '@ant-design/icons';
import styled from 'styled-components';

interface DocumentWrapperProps {
  expanded?: boolean;
  className?: string;
}

const DocumentWrapper = styled.div<DocumentWrapperProps>`
  background-image: url('https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*AnNuRJzJj3MAAAAAQlAAAAgAeprcAQ/original'),
    linear-gradient(180deg, #ffffff 0%, #ffffff00 100%);
  background-repeat: no-repeat;
  background-position: top center;
  background-size: ${(props) =>
    props.expanded ? '566px 150px' : '194px 34px'};
  box-shadow: 0px 2px 6px 0px #000a1a08;
  transition: height 0.3s ease;
  background-color: #fff;
  width: ${(props) => (props.expanded ? '570px' : '194px')};
  max-height: 450px;
  padding: 8px 16px;
  border-radius: ${(props) => (props.expanded ? '12px' : '75px')};

  .document_header {
    font-size: 16px;
    color: #000a1ae3;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    .document_title {
      display: flex;
      align-items: center;
    }
    span {
      font-size: 14px;
      color: #000a1aad;
      line-height: 22px;
      text-align: right;
      display: flex;
      align-items: center;
      gap: 4px;
      font-weight: normal;
    }
  }
  .document_content {
    overflow-y: scroll;
    height: 300px;
    .ant-tree {
      background-color: transparent;
    }
  }
`;

interface TreeNode {
  title: string;
  key: string;
  children?: TreeNode[];
}

interface DirectoryTreeProps {
  data?: {
    uid: string;
    dynamic: boolean;
    markdown: string;
    type?: 'all' | 'incr' | null;
  };
}

const VisLsCard: React.FC<DirectoryTreeProps> = ({ data }) => {
  const [expanded, setExpanded] = useState(true);

  if (!data) return null;
  let treeData: TreeNode[] = [];
  try {
    const parsedData = JSON.parse(data.markdown);
    if (Array.isArray(parsedData)) treeData = parsedData;
  } catch {
    treeData = [];
  }

  if (treeData.length === 0) {
    return <Empty description="暂无数据" />;
  }

  return (
    <DocumentWrapper expanded={expanded}>
      <div className="document_header" onClick={() => setExpanded(!expanded)}>
        <div className="document_title">
          <img
            style={{ height: 22, verticalAlign: '-4px', marginRight: 6 }}
            src="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*HOaXQ785mB4AAAAAQDAAAAgAeprcAQ/original"
            alt=""
          />
          文档目录
        </div>
        <span>
          {expanded ? '收起' : '查看'}
          {expanded ? <UpOutlined /> : <DownOutlined />}
        </span>
      </div>
      {expanded && <Divider style={{ margin: '8px 0 8px' }} />}
      {expanded && (
        <div className="document_content">
          <Tree
            treeData={treeData}
            blockNode
            showLine={{ showLeafIcon: true }}
            showIcon={false}
          />
        </div>
      )}
    </DocumentWrapper>
  );
};

export default VisLsCard;
