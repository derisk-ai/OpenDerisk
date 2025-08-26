import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface AvatarProps {
  src: string;
  width?: string | number;
  className?: string;
}

declare namespace NEXA_API {
  interface Result_List_String__ {
    success?: boolean;
    /** 获取错误码 */
    errorCode?: string;
    /** 获取错误信息 */
    errorMessage?: string;
    /** 获取返回数据 */
    data?: Array<string>;
    traceId?: string;
    host?: string;
  }
}

const Avatar: React.FC<AvatarProps> = React.memo(
  ({ src, width = '32px', className }) => {
    const [avatarUrl, setAvatarUrl] = useState<string>(src);

    return (
      <div style={{ width, height: width }} className={className}>
        {avatarUrl && (
          <img
            src={src || '/agents/default_avatar.png'}
            style={{
              width,
              height: width,
              borderRadius: '50%',
              objectFit: 'cover',
            }}
          />
        )}
      </div>
    );
  },
);

export default Avatar;
