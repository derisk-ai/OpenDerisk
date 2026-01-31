import React from 'react';
import { Image } from 'antd';
import { VisReadYuqueCardWrap } from './style';

const newFileType: Record<string, string> = {
  yuque: 'yuque',
  document: 'file',
  code_wiki: 'wiki',
  monitor: 'monitor',
};

function getFileIcon(type: string, _operation: string): string {
  const icons: Record<string, string> = {
    yuque:
      'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*Yf68SInL2E8AAAAAAAAAAAAADprcAQ/original',
    file: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*HOaXQ785mB4AAAAAQDAAAAgAeprcAQ/original',
    wiki: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*HOaXQ785mB4AAAAAQDAAAAgAeprcAQ/original',
    monitor:
      'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*HOaXQ785mB4AAAAAQDAAAAgAeprcAQ/original',
  };
  return icons[type] || icons.file;
}

interface IProps {
  data: {
    operation?: string;
    datasource?: string;
    monitor_image_url?: string;
    url?: string;
    doc_id?: string;
    repo?: string;
    file_id?: string;
    monitor_id?: string;
    image_id?: string;
  };
  onConnectDocument?: (payload: Record<string, unknown>) => void;
}

const SafeImage: React.FC<{ src?: string; alt?: string; width?: number }> = (
  props,
) => (
  <div onClick={(e) => e.stopPropagation()}>
    <Image {...props} />
  </div>
);

const VisReadYuqueCard = ({ data, onConnectDocument }: IProps) => {
  const { operation, datasource, monitor_image_url } = data;

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    const url = data?.url;
    if (url && url.includes('yuque')) {
      const urlObj = new URL(url);
      const pathParts = urlObj.pathname.split('/').filter((part) => part);
      if (pathParts.length >= 3) {
        onConnectDocument?.({
          groupLogin: pathParts[0],
          docSlug: pathParts[1],
          docUrl: pathParts[2],
        });
      }
    } else if (data?.doc_id) {
      onConnectDocument?.({ docId: data.doc_id, repo: data.repo });
    } else if (data?.file_id) {
      onConnectDocument?.({ fileId: data.file_id });
    } else if (data?.monitor_id) {
      onConnectDocument?.({
        monitorId: data.monitor_id,
        imageId: data.image_id,
      });
    }
  };

  return (
    <VisReadYuqueCardWrap onClick={handleClick}>
      <div className="read-yuque-card">
        {newFileType[datasource || 'yuque'] === 'monitor' ? (
          <div>
            <SafeImage
              src={monitor_image_url}
              alt={operation as string}
              width={68}
            />
            <div className="des">{operation}</div>
          </div>
        ) : (
          <span className="other">
            <img
              src={getFileIcon(
                newFileType[datasource || 'yuque'],
                operation as string,
              )}
              style={{ height: '18px', width: '18px', marginRight: 4 }}
              alt=""
            />
            {operation}
          </span>
        )}
      </div>
    </VisReadYuqueCardWrap>
  );
};

export default VisReadYuqueCard;
