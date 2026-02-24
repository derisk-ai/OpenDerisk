import React from 'react';
import { Skeleton } from 'antd';
import {
  ReportContainer,
  ExportContainer,
  ContentWrapper,
  ReportTitle,
} from './style';

interface VisDocReportCardProps {
  data: {
    title: string;
    markdown?: string;
    description?: string;
    state?: 'running' | 'todo' | 'complete';
    doc_type?: 'spec' | 'yuque';
  };
  onOpenPanel?: (payload: { actionName: string; data: unknown }) => void;
  onExportToYuque?: (payload: { title: string; markdown: string }) => void;
  onExportToKnowledge?: (payload: { title: string; markdown: string }) => void;
}

const VisDocReportCard: React.FC<VisDocReportCardProps> = ({
  data,
  onOpenPanel,
  onExportToYuque,
  onExportToKnowledge,
}) => {
  const { title, markdown, description, state = 'complete', doc_type } = data;
  const content =
    '```drsk-doc\n' +
    JSON.stringify({ markdown, title, doc_type }) +
    '\n```';

  return (
    <div>
      <ReportContainer
        onClick={() => {
          onOpenPanel?.({
            actionName: 'ShowDocReport',
            data: {
              markdown:
                '```knowledge-space-window\n' +
                JSON.stringify({
                  markdown: content,
                  uid:
                    Math.random().toString(36).substring(2, 15) +
                    Math.random().toString(36).substring(2, 15),
                }) +
                '\n```',
              title,
              doc_type,
            },
          });
        }}
      >
        <ContentWrapper>
          <ReportTitle>
            <div className="report-title">
              <img
                className="yuque-icon"
                src="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*Yf68SInL2E8AAAAAAAAAAAAADprcAQ/original"
                alt=""
              />
              <span className="title-text">
                {state === 'running' ? '文档生成中...' : title}
              </span>
            </div>
            {state === 'running' ? (
              <Skeleton
                active
                style={{ marginTop: 8 }}
                paragraph={{ rows: 2 }}
              />
            ) : (
              <div className="description">{description || '-'}</div>
            )}
          </ReportTitle>
          <img
            src="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*1TweTbIHG8wAAAAAQFAAAAgAeprcAQ/original"
            style={{ height: '118px' }}
            alt=""
          />
        </ContentWrapper>
      </ReportContainer>
      {markdown && (
        <ExportContainer>
          <div style={{ color: '#000a1ae3' }}>导出到:</div>
          <div className="export-list">
            <div
              className="yuque-item"
              onClick={(e) => {
                e.stopPropagation();
                onExportToYuque?.({ title, markdown });
              }}
            >
              <img
                className="yuque-icon"
                src="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*Yf68SInL2E8AAAAAAAAAAAAADprcAQ/original"
                alt=""
              />
              语雀文档
            </div>
            <div
              className="yuque-item"
              onClick={(e) => {
                e.stopPropagation();
                onExportToKnowledge?.({ title, markdown });
              }}
            >
              <img
                className="yuque-icon"
                src="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*gS8ySp3rPtQAAAAAAAAAAAAADprcAQ/original"
                alt=""
              />
              知识库
            </div>
          </div>
        </ExportContainer>
      )}
    </div>
  );
};

export default VisDocReportCard;
