'use client';

import React from 'react';
import { Layout } from 'antd';

const { Content } = Layout;

export default function RiskDashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Layout className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Content className="p-0">
        {children}
      </Content>
    </Layout>
  );
}