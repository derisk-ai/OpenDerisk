import React, { useState } from 'react';
import { VisConfirmCardWrap } from './style';
import {
  codeComponents,
  type MarkdownComponent,
  markdownPlugins,
} from '../../config';
import { GPTVis } from '@antv/gpt-vis';
import { Button, Divider } from 'antd';

interface VisConfirmIProps {
  data: {
    markdown?: string;
    disabled?: boolean;
    extra?: Record<string, unknown>;
  };
  otherComponents?: MarkdownComponent;
  onConfirm?: (extra: unknown) => void;
}

const VisConfirmCard: React.FC<VisConfirmIProps> = ({
  data,
  otherComponents,
  onConfirm,
}) => {
  const [disabled, setDisabled] = useState<boolean>(!!data.disabled);

  return (
    <VisConfirmCardWrap className="VisConfirmCardClass">
      <div className="card-content">
        <span className="confirm-title">🎯执行操作确认</span>
        <Divider
          style={{
            margin: '8px 0px 8px 0px',
            borderWidth: '1px',
            borderColor: 'rgba(0, 0, 0, 0.03)',
          }}
        />
        <div className="whitespace-normal">
          {/* @ts-ignore */}
          <GPTVis
            className="whitespace-normal"
            components={{ ...codeComponents, ...(otherComponents || {}) }}
            {...markdownPlugins}
          >
            {data?.markdown || '-'}
          </GPTVis>
        </div>
        <Divider
          style={{
            margin: '8px 0px 8px 0px',
            borderWidth: '1px',
            borderColor: 'rgba(0, 0, 0, 0.03)',
          }}
        />
        <div className="confirm-footer">
          <Button
            disabled={disabled}
            type="primary"
            style={
              !disabled
                ? {
                    backgroundImage:
                      'linear-gradient(104deg, #3595ff 13%, #185cff 99%)',
                    color: '#ffffff',
                  }
                : undefined
            }
            onClick={() => {
              onConfirm?.(data?.extra ?? {});
              setDisabled(true);
            }}
          >
            确认执行
          </Button>
        </div>
      </div>
    </VisConfirmCardWrap>
  );
};

export default VisConfirmCard;
