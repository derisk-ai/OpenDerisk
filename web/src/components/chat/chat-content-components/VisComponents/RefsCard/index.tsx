import React from "react";
import { Tag, Space } from 'antd';
import { RefsCardWrap } from './style';

interface RefItem {
  ref_index: number,
  ref_link: string | undefined,
  ref_name: string | undefined
}

interface Iprops {
  data: Array<RefItem>
}

const RefsCard = ({ data }: Iprops) => {

  return (
    <RefsCardWrap>
      {
        data && data?.length > 0 && (
          <Space wrap style={{ width: '100%' }}>
            <span>参考:&nbsp;</span>
            {
              data?.map((item: RefItem) => (
                <Tag
                  key={item?.ref_link}
                  className="refItem"
                  onClick={() => window.open(item?.ref_link)}
                >
                  <span>{item?.ref_index}</span>
                  <span style={{ margin: '0 4px', color: '#1b62ff31' }}>|</span>
                  <span>{item?.ref_name}</span>
                </Tag>
              ))
            }
          </Space>
        )
      }
    </RefsCardWrap>
  )
};

export default RefsCard;