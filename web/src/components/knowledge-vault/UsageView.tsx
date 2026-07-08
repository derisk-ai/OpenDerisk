'use client';

import { apiInterceptors } from '@/client/api';
import { listIngestJobs, llmUsageSummary } from '@/client/api/knowledge-vault';
import type { IngestJob, LlmUsageSummary } from '@/types/knowledge-vault';
import { Empty, Spin, Tag, Tooltip, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useCallback, useEffect, useState } from 'react';
import { useSpace } from './SpaceContext';

// Task names produced by the ingest pipeline (see ingest.py _call_llm task_name).
const TASK_LABEL: Record<string, string> = {
  extract: '抽取',
  wiki_generate: '生成 wiki',
  entity_curate: '实体整理',
  curate: '整理',
};

const STATUS_LABEL: Record<string, string> = {
  pending: '排队中',
  extracting: '抽取中',
  embedding: '向量化',
  generating_wiki: '生成 wiki',
  curating: '整理中',
  done: '完成',
  failed: '失败',
};

const STATUS_COLOR: Record<string, string> = {
  pending: 'default',
  extracting: 'processing',
  embedding: 'processing',
  generating_wiki: 'processing',
  curating: 'processing',
  done: 'success',
  failed: 'error',
};

function fmtNum(n: number) {
  if (n == null) return '0';
  return n.toLocaleString('en-US');
}

function fmtDate(s: string) {
  if (!s) return '-';
  // backend returns "YYYY-MM-DDTHH:MM:SS"
  return s.replace('T', ' ');
}

/**
 * A horizontal bar showing one bucket's share of a total.
 * Used for by_task / by_model breakdowns.
 */
function ShareBar({
  label,
  value,
  total,
  color = '#0C75FC',
}: {
  label: string;
  value: number;
  total: number;
  color?: string;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <span className="w-24 flex-shrink-0 truncate text-gray-600" title={label}>
        {label}
      </span>
      <div className="flex-1 min-w-0 h-4 bg-gray-50 rounded overflow-hidden">
        <div
          className="h-full rounded transition-all"
          style={{ width: `${pct}%`, backgroundColor: color, opacity: 0.85 }}
        />
      </div>
      <span className="w-20 flex-shrink-0 text-right text-gray-500 tabular-nums">
        {fmtNum(value)} · {pct}%
      </span>
    </div>
  );
}

/** by_task / by_model come back as { tokens, calls, ... } dicts. */
function getToken(map: Record<string, Record<string, number>> | undefined): Record<string, number> {
  if (!map) return {};
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(map)) {
    out[k] = Number(v?.tokens ?? v?.total_tokens ?? 0);
  }
  return out;
}

export default function UsageView({ slug }: { slug: string }) {
  const { refreshKey } = useSpace();
  const [summary, setSummary] = useState<LlmUsageSummary | null>(null);
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [, s] = await apiInterceptors(llmUsageSummary(slug));
      const [, j] = await apiInterceptors(listIngestJobs(slug, 100));
      setSummary(s || null);
      setJobs(j?.items || []);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      message.error(`加载失败: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const byTask = getToken(summary?.by_task);
  const byModel = getToken(summary?.by_model);
  const taskTotal = Object.values(byTask).reduce((a, b) => a + b, 0);
  const modelTotal = Object.values(byModel).reduce((a, b) => a + b, 0);
  const curateTokens = byTask.entity_curate ?? byTask.curate ?? 0;

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4 custom-scrollbar">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-medium text-gray-700 m-0">Token 用量</h3>
          <Tag color="blue">{fmtNum(summary?.total_tokens ?? 0)} tokens</Tag>
          <Tag>{summary?.total_calls ?? 0} 次调用</Tag>
        </div>
        <Tooltip title="刷新">
          <button
            onClick={load}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-all"
          >
            <ReloadOutlined className={`text-xs ${loading ? 'animate-spin' : ''}`} />
          </button>
        </Tooltip>
      </div>

      <Spin spinning={loading}>
        <div className="flex flex-col gap-4">
          {/* summary cards */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-gray-100 bg-white px-4 py-3">
              <div className="text-[12px] text-gray-400">总 token</div>
              <div className="text-[20px] font-medium text-gray-800 mt-1 tabular-nums">
                {fmtNum(summary?.total_tokens ?? 0)}
              </div>
            </div>
            <div className="rounded-lg border border-gray-100 bg-white px-4 py-3">
              <div className="text-[12px] text-gray-400">总调用次数</div>
              <div className="text-[20px] font-medium text-gray-800 mt-1 tabular-nums">
                {fmtNum(summary?.total_calls ?? 0)}
              </div>
            </div>
            <div className="rounded-lg border border-gray-100 bg-white px-4 py-3">
              <div className="text-[12px] text-gray-400">整理任务 token</div>
              <div className="text-[20px] font-medium text-[#0C75FC] mt-1 tabular-nums">
                {fmtNum(curateTokens)}
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">entity_curate / curate</div>
            </div>
          </div>

          {/* by task / by model breakdowns */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-gray-100 bg-white px-4 py-3">
              <div className="text-[12px] font-medium text-gray-700 mb-2">按任务</div>
              {Object.keys(byTask).length === 0 ? (
                <Empty description="暂无" imageStyle={{ height: 40 }} />
              ) : (
                <div className="flex flex-col gap-1.5">
                  {Object.entries(byTask)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <ShareBar
                        key={k}
                        label={TASK_LABEL[k] || k}
                        value={v}
                        total={taskTotal}
                        color={k === 'entity_curate' || k === 'curate' ? '#B5462E' : '#0C75FC'}
                      />
                    ))}
                </div>
              )}
            </div>
            <div className="rounded-lg border border-gray-100 bg-white px-4 py-3">
              <div className="text-[12px] font-medium text-gray-700 mb-2">按模型</div>
              {Object.keys(byModel).length === 0 ? (
                <Empty description="暂无" imageStyle={{ height: 40 }} />
              ) : (
                <div className="flex flex-col gap-1.5">
                  {Object.entries(byModel)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => (
                      <ShareBar key={k} label={k} value={v} total={modelTotal} color="#6b7280" />
                    ))}
                </div>
              )}
            </div>
          </div>

          {/* per-job table */}
          <div className="rounded-lg border border-gray-100 bg-white overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 text-[12px] font-medium text-gray-700">
              整理任务明细（ingest jobs）
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-gray-400 bg-gray-50/50">
                    <th className="text-left font-normal px-4 py-2">源文件</th>
                    <th className="text-left font-normal px-3 py-2">状态</th>
                    <th className="text-right font-normal px-3 py-2">token</th>
                    <th className="text-left font-normal px-3 py-2 min-w-[180px]">任务分布</th>
                    <th className="text-left font-normal px-3 py-2 min-w-[160px]">模型</th>
                    <th className="text-left font-normal px-3 py-2">开始 / 结束</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.length === 0 && !loading ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-10 text-center text-gray-400">
                        <Empty description="暂无 ingest 任务" imageStyle={{ height: 40 }} />
                      </td>
                    </tr>
                  ) : (
                    jobs.map((j) => {
                      const hasCurate =
                        (j.by_task?.entity_curate ?? 0) > 0 || (j.by_task?.curate ?? 0) > 0;
                      return (
                        <tr
                          key={j.id}
                          className="border-t border-gray-50 hover:bg-gray-50/40"
                        >
                          <td className="px-4 py-2.5">
                            <div className="flex items-center gap-1.5">
                              <span className="text-gray-700 truncate max-w-[220px]" title={j.source_file}>
                                {j.source_file || '(无)'}
                              </span>
                              {hasCurate && (
                                <Tag color="red" className="!text-[10px] !px-1 !py-0 !m-0">
                                  整理
                                </Tag>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-2.5">
                            <Tag color={STATUS_COLOR[j.status] || 'default'} className="!m-0">
                              {STATUS_LABEL[j.status] || j.status}
                            </Tag>
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-gray-700">
                            {fmtNum(j.total_tokens)}
                          </td>
                          <td className="px-3 py-2.5">
                            <DistBadges data={j.by_task} labels={TASK_LABEL} curateKeys={['entity_curate', 'curate']} />
                          </td>
                          <td className="px-3 py-2.5">
                            <DistBadges data={j.by_model} />
                          </td>
                          <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">
                            <div>{fmtDate(j.started_at)}</div>
                            {j.finished_at && <div className="text-[10px]">→ {fmtDate(j.finished_at)}</div>}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="text-[11px] text-gray-400 leading-relaxed">
            整理任务在 ingest 流水线内执行（task_name = entity_curate），token 与模型由 llm_call_log 记录。
            注：cron 触发的全量记忆整理（curate_space）目前不记录 token，故不在此展示。
          </div>
        </div>
      </Spin>
    </div>
  );
}

/** tiny inline breakdown: "实体整理 1.2k · 生成 wiki 800" */
function DistBadges({
  data,
  labels,
  curateKeys,
}: {
  data?: Record<string, number>;
  labels?: Record<string, string>;
  curateKeys?: string[];
}) {
  const entries = Object.entries(data || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return <span className="text-gray-300">-</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([k, v]) => (
        <span
          key={k}
          className={[
            'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]',
            curateKeys?.includes(k)
              ? 'bg-[#B5462E]/10 text-[#B5462E]'
              : 'bg-gray-100 text-gray-500',
          ].join(' ')}
        >
          {labels?.[k] || k}
          <span className="tabular-nums">{fmtNum(v)}</span>
        </span>
      ))}
    </div>
  );
}