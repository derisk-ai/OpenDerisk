'use client';

import React, { FC, useMemo, useState } from 'react';
import { Table, Pagination, Tooltip, Button } from 'antd';
import { CopyOutlined, CheckOutlined, DownloadOutlined, DatabaseOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { ManusExecutionOutput } from '@/types/manus';
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

interface IProps {
  outputs: ManusExecutionOutput[];
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

const SqlQueryRenderer: FC<IProps> = ({ outputs }) => {
  const sqlData = useMemo<SqlQueryData | null>(() => {
    const sqlOutput = outputs.find((o) => o.output_type === 'sql_query');
    if (sqlOutput?.content && typeof sqlOutput.content === 'object') {
      return sqlOutput.content as SqlQueryData;
    }
    // Try parsing from string
    if (sqlOutput?.content && typeof sqlOutput.content === 'string') {
      try {
        return JSON.parse(sqlOutput.content);
      } catch {
        return null;
      }
    }
    return null;
  }, [outputs]);

  const [currentPage, setCurrentPage] = useState(sqlData?.page || 1);
  const [copied, setCopied] = useState(false);

  if (!sqlData) {
    // Fallback: show raw output as text
    const text = outputs.map((o) => String(o.content || '')).join('\n');
    return (
      <div className="p-4 text-sm text-gray-600 whitespace-pre-wrap font-mono">
        {text || 'No SQL result data'}
      </div>
    );
  }

  const {
    sql,
    db_name,
    db_type,
    dialect,
    columns,
    rows,
    total_rows,
    total_pages,
    page_size,
    csv_file,
    csv_export_reason,
    raw_result,
  } = sqlData;

  const dbTypeColor = DB_TYPE_COLORS[db_type?.toLowerCase()] || 'bg-gray-50 text-gray-600 border-gray-200';

  const handleCopySql = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy SQL:', err);
    }
  };

  // Build table columns
  const tableColumns: ColumnsType<any> = useMemo(() => {
    if (!columns || columns.length === 0) return [];
    return columns.map((col) => ({
      title: col,
      dataIndex: col,
      key: col,
      ellipsis: true,
      render: (value: any) => {
        if (value === null || value === undefined) {
          return <span className="text-gray-400 italic text-xs">NULL</span>;
        }
        if (typeof value === 'object') {
          return <code className="text-xs bg-gray-50 px-1 rounded">{JSON.stringify(value)}</code>;
        }
        return <span className="text-xs">{String(value)}</span>;
      },
    }));
  }, [columns]);

  // Build table data
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

  // No tabular data — show raw result
  if (!columns || columns.length === 0) {
    return (
      <div className="flex flex-col h-full">
        {/* Header */}
        <SqlHeader
          dbType={db_type}
          dbName={db_name}
          dialect={dialect}
          dbTypeColor={dbTypeColor}
          sql={sql}
          copied={copied}
          onCopy={handleCopySql}
        />
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
    <div className="flex flex-col h-full">
      {/* Header */}
      <SqlHeader
        dbType={db_type}
        dbName={db_name}
        dialect={dialect}
        dbTypeColor={dbTypeColor}
        sql={sql}
        copied={copied}
        onCopy={handleCopySql}
      />

      {/* Results */}
      <div className="flex-1 overflow-auto px-4 pb-4">
        {/* Row count + CSV link */}
        <div className="flex items-center justify-between py-2">
          <span className="text-xs text-gray-500">
            共 {total_rows} 行
            {total_pages > 1 && ` · 第 ${currentPage}/${total_pages} 页`}
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

        {/* Table */}
        <Table
          dataSource={tableData}
          columns={tableColumns}
          rowKey="_key"
          pagination={false}
          size="small"
          scroll={{ x: 'max-content' }}
          className="text-sm [&_.ant-table-thead>tr>th]:bg-gray-50 [&_.ant-table-thead>tr>th]:text-xs [&_.ant-table-thead>tr>th]:font-semibold [&_.ant-table-thead>tr>th]:text-gray-600"
        />

        {/* Pagination */}
        {total_pages > 1 && (
          <div className="mt-3 flex justify-center">
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

/** SQL Header bar — matches the screenshot layout */
const SqlHeader: FC<{
  dbType: string;
  dbName: string;
  dialect?: string;
  dbTypeColor: string;
  sql: string;
  copied: boolean;
  onCopy: () => void;
}> = ({ dbType, dbName, dialect, dbTypeColor, sql, copied, onCopy }) => (
  <div className="border-b border-gray-100">
    {/* Top bar: SQL Query label + badges + Copy */}
    <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50/80">
      <div className="flex items-center gap-2 min-w-0">
        <DatabaseOutlined className="text-gray-400 text-sm flex-shrink-0" />
        <span className="text-[13px] font-medium text-gray-700 flex-shrink-0">SQL Query</span>
        <span className="text-[11px] text-gray-400 flex-shrink-0">
          {(dialect || dbType)?.toUpperCase()}
        </span>
        <span
          className={classNames(
            'text-[10px] font-medium px-1.5 py-0.5 rounded border flex-shrink-0',
            dbTypeColor,
          )}
        >
          {dbName}
        </span>
        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-50 text-red-500 border border-red-200 flex-shrink-0">
          READ ONLY
        </span>
      </div>
      <Tooltip title={copied ? '已复制' : '复制 SQL'}>
        <Button
          type="text"
          size="small"
          className="flex-shrink-0 text-gray-400 hover:text-gray-600"
          icon={copied ? <CheckOutlined className="text-green-500" /> : <CopyOutlined />}
          onClick={onCopy}
        >
          <span className="text-xs ml-0.5">Copy</span>
        </Button>
      </Tooltip>
    </div>

    {/* SQL code area */}
    <pre className="px-4 py-3 bg-slate-900 text-[13px] text-slate-100 overflow-x-auto max-h-40 leading-relaxed">
      <code>{sql}</code>
    </pre>
  </div>
);

export default SqlQueryRenderer;
