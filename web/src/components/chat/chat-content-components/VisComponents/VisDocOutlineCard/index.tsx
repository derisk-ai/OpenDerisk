import { PlusOutlined, DownOutlined, UpOutlined } from '@ant-design/icons';
import { Button, Card, Typography, Skeleton } from 'antd';
import React, { useState } from 'react';
import { VisDocOutlinedWrap } from './style';

interface DocOutlineItem {
  title: string;
  summary?: string;
  state?: 'running' | 'todo' | 'complete';
  children?: DocOutlineItem[];
}

interface VisDocOutlineIProps {
  data: DocOutlineItem;
}

const OutlineCard: React.FC<{
  data: DocOutlineItem;
  level?: number;
  index?: number;
  parentIndex?: string;
  currentHoverId: string | null;
  onHover: (id: string | null) => void;
}> = ({ data, level = 0, currentHoverId, onHover }) => {
  const isHovered = currentHoverId === data.title;
  const hasChildren = data.children && data.children.length > 0;
  const displayTitle = data.title;
  const indent = level * 4;

  return (
    <div
      className={`outline-item level-${level} ${isHovered ? 'highlighted' : ''}`}
      style={{ paddingLeft: indent, marginTop: 8 }}
      onMouseEnter={() => onHover(data.title)}
      onMouseLeave={() => onHover(null)}
    >
      <div
        className="outline-card"
        style={{
          padding: '8px 12px',
          borderRadius: 6,
          backgroundColor: isHovered ? '#f0f0f0' : 'transparent',
          borderColor: isHovered ? '#91d5ff' : '#d9d9d9',
          cursor: 'pointer',
        }}
      >
        <Typography.Text strong>{displayTitle}</Typography.Text>
        <div className="outline-summary">
          {data.summary && (
            <Typography.Paragraph
              type="secondary"
              style={{ fontSize: 13, margin: '4px 0 0 0', color: '#000a1aad' }}
            >
              {data.summary}
            </Typography.Paragraph>
          )}
        </div>
        {hasChildren &&
          data?.children?.map((item, idx) => (
            <OutlineCard
              key={item.title}
              data={item}
              level={level + 1}
              index={idx}
              parentIndex=""
              currentHoverId={currentHoverId}
              onHover={onHover}
            />
          ))}
      </div>
    </div>
  );
};

export const VisDocOutlineCard: React.FC<VisDocOutlineIProps> = ({ data }) => {
  const [currentHoverId, setCurrentHoverId] = useState<string | null>(null);
  const [expand, setExpand] = useState<boolean>(false);

  return (
    <VisDocOutlinedWrap>
      <Card
        className="document-outline-card"
        title={
          <div className="card-header">
            <Typography.Text strong>
              <img
                className="header-icon"
                src="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*fGI9R7c08hAAAAAAQBAAAAgAeprcAQ/original"
                alt=""
              />
              <span>文档框架</span>
            </Typography.Text>
          </div>
        }
        extra={
          <div className="reload-text">
            <img
              src="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*Rbb0S5b2ihMAAAAAQCAAAAgAeprcAQ/original"
              alt=""
            />
            重新生成
          </div>
        }
      >
        {data.state === 'running' ? (
          <Skeleton active />
        ) : (
          <div>
            <div className="article-title-container">
              <div className="article-title">{data.title}</div>
            </div>
            <div
              className="outline-content"
              style={expand ? {} : { height: '400px', overflow: 'auto' }}
            >
              {data.children &&
                data.children.map((item, index) => (
                  <OutlineCard
                    key={item.title}
                    data={item}
                    level={0}
                    index={index}
                    currentHoverId={currentHoverId}
                    onHover={setCurrentHoverId}
                  />
                ))}
            </div>
            <div
              className="footer-text"
              onClick={() => setExpand(!expand)}
              style={{ cursor: 'pointer' }}
            >
              {expand ? <UpOutlined /> : <DownOutlined />}
              {expand ? '收起文档框架' : '展开文档框架'}
            </div>
            <div className="footer-btn">
              <Button
                disabled
                style={{ borderRadius: 18 }}
                icon={<PlusOutlined />}
                type="dashed"
                block
              >
                增加章节
              </Button>
              <Button disabled type="primary" style={{ width: '120px' }}>
                确认框架
              </Button>
            </div>
          </div>
        )}
      </Card>
    </VisDocOutlinedWrap>
  );
};

export default VisDocOutlineCard;
