import { Button, Card, Space } from 'antd';
import React, { useState } from 'react';
import { VisReportCardWrap } from './style';
import { markdownComponents, markdownPlugins } from '../../config';
import { GPTVisLite } from '@antv/gpt-vis';
import { VisCardWrap } from '../style';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

interface IProps {
  data: {
    markdown: string;
  };
  title?: string;
  downloadButton?: boolean;
  extraMenu?: React.ReactNode;
}

const VisReportCard = ({
  data,
  extraMenu,
  title = '总结报告',
  downloadButton = true,
}: IProps) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleDownload = async () => {
    setIsLoading(true);

    const container: HTMLElement = document.querySelector(
      '.DownCardClass',
    ) as HTMLElement;
    if (!container) {
      console.error('Container not found!');
      setIsLoading(false);
      return;
    }

    try {
      const canvas = await html2canvas(container, {
        useCORS: true,
      });

      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF();

      const imgWidth = pdf.internal.pageSize.getWidth() - 20;
      const pageHeight = pdf.internal.pageSize.getHeight() - 20;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;

      const totalPages = Math.ceil(imgHeight / pageHeight);
      Array.from({ length: totalPages }).forEach((_, index) => {
        const position = -pageHeight * index + 10;
        pdf.addImage(imgData, 'PNG', 10, position, imgWidth, imgHeight);
        if (index < totalPages - 1) {
          pdf.addPage();
        }
      });

      pdf.save('report.pdf');
    } catch (error) {
      console.error('下载PDF出错:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const TitleAction = () => (
    <div className="titleActionWrap">
      <Space>
        <div
          style={{
            width: '32px',
            height: '32px',
            padding: '5px 7px',
            background: 'rgb(27 98 255 / 8%)',
            borderRadius: '8px',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          <img
            style={{ width: '18px', height: '22px' }}
            src="/icons/report.svg"
            alt=""
          />
        </div>
        <span>{title}</span>
      </Space>
      <Space>
        {extraMenu}
        {downloadButton && (
          <Button
            loading={isLoading}
            onClick={handleDownload}
            style={{ padding: '4px 6px', fontSize: '14px' }}
          >
            下载报告
          </Button>
        )}
      </Space>
    </div>
  );

  return (
    <VisCardWrap>
      <VisReportCardWrap>
        <Card
          title={<TitleAction />}
          variant="borderless"
          style={{ width: '100%' }}
        >
          <div className="DownCardClass">
            {/* @ts-ignore */}
            <GPTVisLite
              className="whitespace-normal"
              components={markdownComponents}
              {...markdownPlugins}
            >
              {data?.markdown || '-'}
            </GPTVisLite>
          </div>
        </Card>
      </VisReportCardWrap>
    </VisCardWrap>
  );
};

export default VisReportCard;
