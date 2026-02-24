import { Button, Card, Space } from 'antd';
import React, { memo, useState } from 'react';
import { VisDocCardWrap } from './style';
import {
  codeComponents,
  type MarkdownComponent,
  markdownPlugins,
} from '../../config';
import { GPTVis } from '@antv/gpt-vis';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

interface IProps {
  data: {
    markdown: string;
    state?: 'running' | 'todo' | 'complete';
    title?: string;
    avatar?: string;
    doc_type?: string;
  };
  downloadButton?: boolean;
  extraMenu?: React.ReactNode;
  otherComponents?: MarkdownComponent;
}

interface TitleActionProps {
  title: string;
  extraMenu?: React.ReactNode;
  downloadButton?: boolean;
  isLoading: boolean;
  avatar?: string;
  handleDownload: () => void;
}

const TitleAction = memo(
  ({
    title = '生成文档',
    extraMenu,
    downloadButton,
    isLoading,
    avatar,
    handleDownload,
  }: TitleActionProps) => (
    <div className="titleActionWrap">
      <Space>
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          {avatar && (
            <img style={{ height: '24px' }} src={avatar} alt="" />
          )}
        </div>
        <span>{title}</span>
      </Space>
      <Space size={18}>
        {extraMenu}
        {downloadButton && (
          <Button
            loading={isLoading}
            onClick={handleDownload}
            style={{ padding: '4px 6px', fontSize: '14px' }}
          >
            下载文档
          </Button>
        )}
      </Space>
    </div>
  ),
);

const VisDocCard = ({
  data,
  extraMenu,
  downloadButton = true,
  otherComponents,
}: IProps) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleDownload = async () => {
    setIsLoading(true);
    const container = document.querySelector(
      '.DownCardClass',
    ) as HTMLElement;
    if (!container) {
      setIsLoading(false);
      return;
    }
    try {
      const canvas = await html2canvas(container, { useCORS: true });
      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF();
      const imgWidth = pdf.internal.pageSize.getWidth() - 20;
      const pageHeight = pdf.internal.pageSize.getHeight() - 20;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;
      const totalPages = Math.ceil(imgHeight / pageHeight);
      Array.from({ length: totalPages }).forEach((_, index) => {
        const position = -pageHeight * index + 10;
        pdf.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight);
        if (index < totalPages - 1) pdf.addPage();
      });
      pdf.save('report.pdf');
    } catch (error) {
      console.error('下载PDF出错:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const customComponents = {
    h1: (props: any) => (
      <h1
        className="doc-title"
        {...props}
        style={{
          position: 'relative',
          textAlign: data.doc_type === 'spec' ? 'left' : 'center',
          borderBottom: data.doc_type === 'spec' ? 'none' : '2px solid #000a1a12',
        }}
      >
        {props.children}
        {data.doc_type === 'spec' ? null : (
          <div className="title-bottom-divider" />
        )}
      </h1>
    ),
    h2: (props: any) => <h2 className="doc-subtitle" {...props} />,
    h3: (props: any) => (
      <h3 className="doc-section" {...props}>
        <div className="blue-double-ring" />
        {props.children}
      </h3>
    ),
  };

  return (
    <VisDocCardWrap>
      <div style={{ width: '100%' }}>
        <Card
          title={
            <TitleAction
              title={data?.title as string}
              avatar={data?.avatar as string}
              extraMenu={extraMenu}
              downloadButton={downloadButton}
              isLoading={isLoading}
              handleDownload={handleDownload}
            />
          }
          variant="borderless"
          style={{ width: '100%', boxShadow: 'none' }}
        >
          {data?.state === 'running' ? (
            <img
              src="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*DOaJRp9V4K4AAAAASlAAAAgAeprcAQ/original"
              alt=""
            />
          ) : (
            <div className="DownCardClass">
              {/* @ts-ignore */}
              <GPTVis
                className="whitespace-normal"
                components={{
                  ...codeComponents,
                  ...(otherComponents || {}),
                  ...customComponents,
                }}
                {...markdownPlugins}
              >
                {data?.markdown || ''}
              </GPTVis>
            </div>
          )}
        </Card>
      </div>
    </VisDocCardWrap>
  );
};

export default VisDocCard;
