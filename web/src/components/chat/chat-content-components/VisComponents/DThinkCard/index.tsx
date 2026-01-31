import { DownOutlined } from '@ant-design/icons';
import { Space, Typography } from 'antd';
import React, { useEffect, useState } from 'react';
import { DThinkCardWrap } from './style';

import {
  codeComponents,
  type MarkdownComponent,
  markdownPlugins,
} from '../../config';
import { GPTVis } from '@antv/gpt-vis';

interface DThinkCardProps {
  data: any;
  otherComponents?: MarkdownComponent;
  style?: React.CSSProperties;
  collapseTitle?: string;
  showExtra?: boolean;
  extraTitle?: string;
  extraClick?: (thinkData: any) => void;
  expand?: boolean;
}

const DThinkCard: React.FC<DThinkCardProps> = ({
  data,
  style,
  collapseTitle = '深度思考过程',
  otherComponents,
  expand = true,
}) => {
  const [active, setActive] = useState(true);

  // 同步外部传入的展开状态
  useEffect(() => {
    setActive(expand);
  }, [expand]);

  return (
    <DThinkCardWrap
      style={{ background: 'transparent', ...(style || {}) }}
      className="DThinkCardClass"
    >
      <div className="d-thinking-title" onClick={() => setActive(!active)}>
        <Typography.Text>
          <Space>
            <span>{collapseTitle}</span>
            <DownOutlined className={active ? 'rotate' : 'd-icon'} />
          </Space>
        </Typography.Text>
      </div>
      <div
        className="d-thinking-content"
        style={{ display: active ? 'block' : 'none' }}
      >
        <Typography.Paragraph>
          <blockquote>
            <Typography.Text type="secondary">
              {/* @ts-ignore */}
              <GPTVis
                className="whitespace-normal"
                components={{ ...codeComponents, ...(otherComponents || {}) }}
                {...markdownPlugins}
              >
                {data?.markdown || '-'}
              </GPTVis>
            </Typography.Text>
          </blockquote>
        </Typography.Paragraph>
      </div>
    </DThinkCardWrap>
  );
};

export default DThinkCard;

