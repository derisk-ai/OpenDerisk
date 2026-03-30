'use client';

import React from 'react';
import { Card, Row, Col, Statistic, Typography } from 'antd';
import {
  CheckCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { RiskSummary, riskLevelMap } from '../mock/data';

const { Title } = Typography;

interface RiskSummaryProps {
  summary: RiskSummary;
  loading?: boolean;
}

export default function RiskSummaryCard({ summary, loading }: RiskSummaryProps) {
  const { t } = useTranslation();

  const items = [
    {
      key: 'green',
      title: t('risk_level_green'),
      value: summary.greenCount,
      icon: <CheckCircleOutlined style={{ fontSize: 24, color: riskLevelMap.green.color }} />,
      color: riskLevelMap.green.color,
      bgColor: riskLevelMap.green.bgColor,
    },
    {
      key: 'blue',
      title: t('risk_level_blue'),
      value: summary.blueCount,
      icon: <InfoCircleOutlined style={{ fontSize: 24, color: riskLevelMap.blue.color }} />,
      color: riskLevelMap.blue.color,
      bgColor: riskLevelMap.blue.bgColor,
    },
    {
      key: 'yellow',
      title: t('risk_level_yellow'),
      value: summary.yellowCount,
      icon: <WarningOutlined style={{ fontSize: 24, color: riskLevelMap.yellow.color }} />,
      color: riskLevelMap.yellow.color,
      bgColor: riskLevelMap.yellow.bgColor,
    },
    {
      key: 'red',
      title: t('risk_level_red'),
      value: summary.redCount,
      icon: <CloseCircleOutlined style={{ fontSize: 24, color: riskLevelMap.red.color }} />,
      color: riskLevelMap.red.color,
      bgColor: riskLevelMap.red.bgColor,
    },
  ];

  return (
    <Card loading={loading} className="mb-6">
      <Row gutter={[16, 16]}>
        {items.map((item) => (
          <Col xs={12} sm={6} key={item.key}>
            <div
              className="p-4 rounded-lg"
              style={{ backgroundColor: item.bgColor }}
            >
              <div className="flex items-center gap-2 mb-2">
                {item.icon}
                <span style={{ color: item.color, fontWeight: 500 }}>{item.title}</span>
              </div>
              <div className="text-2xl font-bold" style={{ color: item.color }}>
                {item.value} <span className="text-sm font-normal">{t('risk_entity_count')}</span>
              </div>
            </div>
          </Col>
        ))}
      </Row>
    </Card>
  );
}