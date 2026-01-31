import React, { FC } from 'react';
import { Tag, Space } from 'antd';
import { AttachWrap } from './style';

interface AttachItem {
  name?: string;
  url?: string;
  link?: string;
  ref_name?: string;
  ref_link?: string;
  [key: string]: unknown;
}

interface IProps {
  data: AttachItem[] | { items?: AttachItem[]; [key: string]: unknown };
}

const VisDAttach: FC<IProps> = ({ data }) => {
  const items = Array.isArray(data)
    ? data
    : (data && (data as { items?: AttachItem[] }).items) ?? [];

  if (!items?.length) {
    return null;
  }

  return (
    <AttachWrap>
      <Space wrap style={{ width: '100%' }}>
        <span>附件：</span>
        {items.map((item: AttachItem, index: number) => {
          const href = item?.url ?? item?.link ?? item?.ref_link;
          const label = item?.name ?? item?.ref_name ?? `附件 ${index + 1}`;
          return (
            <Tag
              key={href ?? index}
              className="attachItem"
              onClick={() => href && window.open(href)}
            >
              {label}
            </Tag>
          );
        })}
      </Space>
    </AttachWrap>
  );
};

export default VisDAttach;
