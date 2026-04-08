'use client';

import React, { FC, useMemo, useState } from 'react';
import { Table, Pagination, Tag, Tooltip, Button, Space } from 'antd';
import {
  DownloadOutlined,
  CopyOutlined,
  CheckOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import classNames from 'classnames';

interface SqlQueryData {
  sql: string;
  db_name: string;
  db_type: string;
  dialect?: string;
  columns: string[];
  rows: Array<Array<any>>;
  total_rows: number;
  page: number;
  total_pages: number;
  page_size: number;
  has_more: boolean;
  csv_file?: string;
  csv_export_reason?: string;
  raw_result?: string;
}

interface VisSqlQueryProps {
  data: SqlQueryData;
}

const DB_TYPE_COLORS: Record<string, string> = {
  sqlite: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  mysql: 'bg-blue-50 text-blue-600 border-blue-200',
  postgresql: 'bg-indigo-50 text-indigo-600 border-indigo-200',
  postgres: 'bg-indigo-50 text-indigo-600 border-indigo-200',
  oracle: 'bg-orange-50 text-orange-600 border-orange-200',
  mssql: 'bg-red-50 text-red-600 border-red-200',
  sqlserver: 'bg-red-50 text-red-600 border-red-200',
  duckdb: 'bg-yellow-50 text-yellow-600 border-yellow-200',
};

const VisSqlQuery: FC<VisSqlQueryProps> = ({ data }) => {
  const {
    sql,
    db_name,
    db_type,
    dialect,
    columns,
    rows,
    total_rows,
    page,
    total_pages,
    page_size,
    has_more,
    csv_file,
    csv_export_reason,
    raw_result,
  } = data;

  const [currentPage, setCurrentPage] = useState(page || 1);
  const [copied, setCopied] = useState(false);

  // Determine badge color based on db_type
  const dbTypeColor = DB_TYPE_COLORS[db_type?.toLowerCase()] || 'bg-gray-50 text-gray-600 border-gray-200';

  // Convert rows to table data
  const tableData = useMemo(() => {
    if (!rows || rows.length === 0) return [];
    return rows.map((row, index) => {
      const record: Record<string, any> = { _key: index };
      columns?.forEach((col, colIndex) => {
        record[col] = row[colIndex];
      });
      return record;
    });
  }, [rows, columns]);

  // Generate table columns
  const tableColumns: ColumnsType<any> = useMemo(() => {
    if (!columns || columns.length === 0) return [];
    return columns.map((col) => ({
      title: col,
      dataIndex: col,
      key: col,
      ellipsis: true,
      render: (value: any) => {
        if (value === null || value === undefined) {
          return <span className="text-gray-400 italic">NULL</span>;
        }
        if (typeof value === 'object') {
          return <code className="text-xs bg-gray-50 px-1 rounded">{JSON.stringify(value)}</code>;
        }
        return String(value);
      },
    }));
  }, [columns]);

  // Copy SQL to clipboard
  const handleCopySql = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy SQL:', err);
    }
  };

  // If no tabular data, show raw result
  if (!columns || columns.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        {/* Header with SQL */}
        <div className="border-b border-gray-100 bg-gray-50 px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <DatabaseOutlined className="text-gray-400" />
              <span className="font-medium text-gray-700">{db_name}</span>
              <Tag className={classNames('text-[10px] font-medium border', dbTypeColor)}>
                {(dialect || db_type)?.toUpperCase()}
              </Tag>
            </div>
            <Tooltip title={copied ? '已复制' : '复制 SQL'}>
              <Button
                type="text"
                size="small"
                icon={copied ? <CheckOutlined className="text-green-500" /> : <CopyOutlined />}
                onClick={handleCopySql}
              />
            </Tooltip>
          </div>
          <pre className="mt-2 text-sm text-gray-600 bg-gray-100 rounded p-2 overflow-x-auto max-h-32">
            <code>{sql}</code>
          </pre>
        </div>
        {/* Result */}
        <div className="p-4">
          {raw_result ? (
            <pre className="text-sm text-gray-600 whitespace-pre-wrap">{raw_result}</pre>
          ) : (
            <div className="text-gray-400 text-sm">查询执行成功，无结果返回。</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header with SQL */}
      <div className="border-b border-gray-100 bg-gray-50 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <DatabaseOutlined className="text-gray-400" />
            <span className="font-medium text-gray-700">{db_name}</span>
            <Tag className={classNames('text-[10px] font-medium border', dbTypeColor)}>
              {(dialect || db_type)?.toUpperCase()}
            </Tag>
          </div>
          <Tooltip title={copied ? '已复制' : '复制 SQL'}>
            <Button
              type="text"
              size="small"
              icon={copied ? <CheckOutlined className="text-green-500" /> : <CopyOutlined />}
              onClick={handleCopySql}
            />
          </Tooltip>
        </div>
        <pre className="mt-2 text-sm text-gray-600 bg-gray-100 rounded p-2 overflow-x-auto max-h-32">
          <code>{sql}</code>
        </pre>
      </div>

      {/* Results table */}
      <div className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs text-gray-500">
            共 {total_rows} 行{total_pages > 1 && ` · 第 ${currentPage}/${total_pages} 页`}
          </span>
          {csv_file && (
            <Tooltip title={csv_export_reason}>
              <a
                href={csv_file}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-500 hover:text-blue-600 flex items-center gap-1"
              >
                <DownloadOutlined className="text-[10px]" />
                下载完整 CSV
              </a>
            </Tooltip>
          )}
        </div>

        <Table
          dataSource={tableData}
          columns={tableColumns}
          rowKey="_key"
          pagination={false}
          size="small"
          scroll={{ x: 'max-content' }}
          className="text-sm"
        />

        {/* Pagination */}
        {total_pages > 1 && (
          <div className="mt-4 flex justify-center">
            <Pagination
              current={currentPage}
              total={total_rows}
              pageSize={page_size}
              onChange={(p) => setCurrentPage(p)}
              showSizeChanger={false}
              showTotal={(total) => `共 ${total} 行`}
              size="small"
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default VisSqlQuery;