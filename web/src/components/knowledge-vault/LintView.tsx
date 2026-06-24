'use client';

import { apiInterceptors } from '@/client/api';
import { lintSpace } from '@/client/api/knowledge-vault';
import type { LintIssue } from '@/types/knowledge-vault';
import {
  Alert,
  Button,
  Empty,
  Spin,
  Tag,
  Tooltip,
  message,
} from 'antd';
import { ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  slug: string;
  onOpenDoc?: (path: string) => void;
  onDeleteVerbat?: (verbatId: string) => void;
}

const SEVERITY_COLOR: Record<string, string> = {
  error: 'red',
  warning: 'orange',
  info: 'blue',
};

const RULE_LABEL: Record<string, string> = {
  orphan_doc: '孤岛文档',
  broken_wikilink: '断链',
  verbat_without_wiki: '无 wiki 派生',
};

export default function LintView({ slug, onOpenDoc, onDeleteVerbat }: Props) {
  const { t } = useTranslation();
  const [issues, setIssues] = useState<LintIssue[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [, data] = await apiInterceptors(lintSpace(slug));
      setIssues(data?.issues || []);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  const counts = issues.reduce(
    (acc, i) => {
      acc[i.severity] = (acc[i.severity] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3 custom-scrollbar">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-medium text-gray-700 m-0">
            {t('knowledge_lint' as any) || '知识库体检'}
          </h3>
          <Tag color="red">{counts.error || 0} error</Tag>
          <Tag color="orange">{counts.warning || 0} warning</Tag>
          <Tag color="blue">{counts.info || 0} info</Tag>
        </div>
        <Tooltip title={t('builder_refresh' as any) || '刷新'}>
          <button
            onClick={load}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-all"
          >
            <ReloadOutlined className={`text-xs ${loading ? 'animate-spin' : ''}`} />
          </button>
        </Tooltip>
      </div>

      <Alert
        type="info"
        showIcon
        message={t('knowledge_lint_hint' as any) || 'v1 仅做结构性体检（孤岛文档、断链、无 wiki 派生）。LLM 语义体检将在 v2 推出。'}
        className="!text-xs"
      />

      <Spin spinning={loading}>
        {issues.length === 0 && !loading ? (
          <Empty
            description={t('knowledge_lint_clean' as any) || '一切就绪，未发现问题'}
            className="py-12"
          />
        ) : (
          <div className="flex flex-col gap-2">
            {issues.map((issue, idx) => (
              <div
                key={idx}
                className="flex items-start gap-3 p-3 rounded-lg border border-gray-100 bg-white hover:border-gray-200"
              >
                <div className="flex-shrink-0 mt-0.5">
                  {issue.severity === 'error' ? (
                    <Tag color="red">error</Tag>
                  ) : issue.severity === 'warning' ? (
                    <Tag color="orange">
                      <WarningOutlined /> warning
                    </Tag>
                  ) : (
                    <Tag color="blue">info</Tag>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[12px] font-medium text-gray-700">
                      {RULE_LABEL[issue.rule] || issue.rule}
                    </span>
                    {issue.path && (
                      <code className="text-[11px] text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded">
                        {issue.path}
                      </code>
                    )}
                    {issue.verbat_id && (
                      <code className="text-[11px] text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded">
                        {issue.verbat_id.slice(0, 16)}…
                      </code>
                    )}
                  </div>
                  <div className="text-[12px] text-gray-500">{issue.message}</div>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  {issue.path && onOpenDoc && (
                    <Button
                      size="small"
                      type="link"
                      onClick={() => onOpenDoc(issue.path!)}
                    >
                      {t('common_open' as any) || '打开'}
                    </Button>
                  )}
                  {issue.verbat_id && onDeleteVerbat && (
                    <Button
                      size="small"
                      type="link"
                      danger
                      onClick={() => onDeleteVerbat(issue.verbat_id!)}
                    >
                      {t('common_delete' as any) || '删除'}
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Spin>
    </div>
  );
}
