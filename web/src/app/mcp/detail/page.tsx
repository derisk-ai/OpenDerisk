"use client"
import { ChatContext } from '@/contexts';
import { apiInterceptors, getMCPListQuery, mcpToolList, mcpToolRun } from '@/client/api';
import { CopyOutlined, RedoOutlined, ArrowLeftOutlined, ThunderboltOutlined } from '@ant-design/icons';
import JsonView from '@uiw/react-json-view';
import { githubDarkTheme } from '@uiw/react-json-view/githubDark';
import { githubLightTheme } from '@uiw/react-json-view/githubLight';
import { useRequest } from 'ahooks';
import { Button, Form, Input, Spin, App, Tooltip } from 'antd';
import { useSearchParams, useRouter } from 'next/navigation';
import React, { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import '../index.css';

export default function McpDetail() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { mode } = useContext(ChatContext);
  const { t } = useTranslation();
  const { message } = App.useApp();

  const [mcpInfo, setMcpInfo] = useState<any>({});
  const [selectUrl, setSelectUrl] = useState<string>('');
  const [runResult, setRunResult] = useState<any>(null);
  const [toolList, setToolList] = useState<Array<{ name: string; description: string; param_schema: any }>>([]);
  const theme = mode === 'dark' ? githubDarkTheme : githubLightTheme;
  const queryParams = {
    id: searchParams.get('id') || '',
    name: searchParams.get('name') || '',
  };
  const [form] = Form.useForm();
  const leftPanelRef = useRef<HTMLDivElement>(null);
  const [rightColumnHeight, setRightColumnHeight] = useState<number | undefined>(undefined);

  useEffect(() => {
    const el = leftPanelRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setRightColumnHeight(entry.target.clientHeight);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const {
    loading: runLoading,
    run: runMcpToolRun,
    data: runData,
  } = useRequest(
    async (params: any): Promise<any> => {
      return await apiInterceptors(mcpToolRun(params));
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          message.success(t('success'));
          if (res?.data !== null && typeof res?.data === 'object') {
            try {
              setRunResult(res || null);
            } catch {
              setRunResult(null);
            }
          }
        }
      },
      debounceWait: 300,
    },
  );

  const { loading: mcpQueryLoading } = useRequest(
    async (): Promise<any> => {
      if (!queryParams.name) return Promise.reject('Missing name parameter');
      return await apiInterceptors(
        getMCPListQuery({ name: queryParams.name }),
      );
    },
    {
      manual: false,
      onSuccess: data => {
        const [, res] = data;
        setMcpInfo(res || {});
      },
      debounceWait: 300,
    },
  );

  const { loading: listLoading, run: runToolList } = useRequest(
    async (params = { name: queryParams.name }): Promise<any> => {
      if (!params.name) return Promise.reject('Missing name parameter');
      return await apiInterceptors(mcpToolList(params));
    },
    {
      manual: false,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.data) {
          setToolList(res?.data || []);
        }
      },
      debounceWait: 300,
    },
  );

  const handleCopy = () => {
    const text = runResult ? JSON.stringify(runResult, null, 2) : '';
    navigator.clipboard
      .writeText(text)
      .then(() => message.success(t('success')))
      .catch(err => message.error(String(err)));
  };

  const handleSelectTool = (key: string) => {
    if (key === selectUrl) return;
    setSelectUrl(key);
    form.resetFields();
    setRunResult(null);
  };

  const handleRefresh = async () => {
    await runToolList({ name: queryParams?.name });
  };

  const onGoRun = async () => {
    if (!selectUrl) {
      message.warning(t('please_select_mcp'));
      return;
    }
    try {
      const values = await form.validateFields();
      await runMcpToolRun({
        name: queryParams?.name,
        params: {
          name: selectUrl,
          arguments: { ...values },
        },
      });
    } catch {
      message.error(t('form_required'));
    }
  };

  const formData: any = useMemo(() => {
    return toolList?.find(item => item?.name === selectUrl)?.param_schema || {};
  }, [selectUrl, toolList]);

  const formKeys = useMemo(() => Object.keys(formData || {}), [formData]);

  if (!queryParams.name || !queryParams.id) {
    return (
      <div className='mcp-detail-root' style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Spin spinning={listLoading || runLoading || mcpQueryLoading}>
      <div className='mcp-detail-root'>
        <div className='mcp-detail-content'>
          {/* Back button */}
          <div style={{ marginBottom: 8 }}>
            <Button
              type='text'
              icon={<ArrowLeftOutlined />}
              onClick={() => router.push('/mcp')}
              style={{ color: 'var(--mcp-text-secondary)', padding: '4px 8px', marginLeft: -8 }}
            >
              {t('mcp_back_to_list')}
            </Button>
          </div>

          {/* Header */}
          <div className='mcp-detail-header'>
            <div className='mcp-detail-avatar'>
              {mcpInfo?.icon ? (
                <img src={mcpInfo?.icon} alt={mcpInfo?.name} />
              ) : (
                <span className='mcp-detail-avatar-fallback'>
                  {(mcpInfo?.name || 'M').charAt(0).toUpperCase()}
                </span>
              )}
            </div>
            <div className='mcp-detail-info'>
              <h1 className='mcp-detail-name'>{mcpInfo?.name}</h1>
              <p className='mcp-detail-desc'>{mcpInfo?.description}</p>
            </div>
          </div>

          {/* Endpoint bar */}
          {mcpInfo?.sse_url && (
            <div className='mcp-endpoint-bar'>
              <div className='mcp-endpoint-method'>SSE</div>
              <div className='mcp-endpoint-url'>{mcpInfo?.sse_url}</div>
              <Tooltip title={t('copy')}>
                <Button
                  type='text'
                  icon={<CopyOutlined />}
                  onClick={() => {
                    navigator.clipboard.writeText(mcpInfo?.sse_url || '');
                    message.success(t('success'));
                  }}
                  style={{ marginRight: 8, color: 'var(--mcp-text-tertiary)' }}
                />
              </Tooltip>
            </div>
          )}

          {/* Split panes: Tools | Params + Results */}
          <div className='mcp-detail-grid'>
            {/* Left: Tool List */}
            <div className='mcp-panel' ref={leftPanelRef}>
              <div className='mcp-panel-header'>
                <span className='mcp-panel-title'>{t('mcp_tools')}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className='mcp-panel-badge'>{toolList?.length || 0}</span>
                  <Button
                    type='text'
                    size='small'
                    icon={<RedoOutlined />}
                    onClick={handleRefresh}
                    style={{ color: 'var(--mcp-text-tertiary)' }}
                  />
                </div>
              </div>
              <div className='mcp-panel-body'>
                {toolList?.length > 0 ? (
                  toolList.map((item, index) => (
                    <div
                      key={index}
                      className={`mcp-tool-item ${selectUrl === item?.name ? 'mcp-tool-item--active' : ''}`}
                      onClick={() => handleSelectTool(item?.name)}
                    >
                      <div className='mcp-tool-name'>{item.name}</div>
                      <div className='mcp-tool-desc'>{item?.description}</div>
                    </div>
                  ))
                ) : (
                  <div className='mcp-result-empty'>
                    {t('mcp_no_tools')}
                  </div>
                )}
              </div>
            </div>

            {/* Right: Params + Results (sticky, 1:1 split, height matches left panel) */}
            <div className='mcp-right-column' style={rightColumnHeight ? { maxHeight: rightColumnHeight } : undefined}>
              {/* Parameters panel - 50% */}
              <div className='mcp-panel mcp-params-panel'>
                <div className='mcp-panel-header'>
                  <span className='mcp-panel-title'>
                    {selectUrl
                      ? selectUrl
                      : t('mcp_select_tool_hint')}
                  </span>
                </div>
                <div className='mcp-form-section'>
                  {selectUrl && formKeys.length > 0 ? (
                    <Form form={form} layout='vertical'>
                      {formKeys.map((item) => (
                        <Form.Item
                          key={item}
                          label={formData?.[item]?.title || item}
                          name={item}
                          rules={[
                            {
                              required: formData?.[item]?.required,
                              message: `${t('please_enter')} ${item}`,
                            },
                          ]}
                          initialValue={formData?.[item]?.default}
                        >
                          <Input placeholder={formData?.[item]?.description} />
                        </Form.Item>
                      ))}
                      <Form.Item style={{ marginBottom: 0 }}>
                        <Button
                          type='primary'
                          icon={<ThunderboltOutlined />}
                          className='mcp-run-btn'
                          onClick={onGoRun}
                          loading={runLoading}
                        >
                          {t('mcp_trial_run')}
                        </Button>
                      </Form.Item>
                    </Form>
                  ) : selectUrl ? (
                    <div>
                      <p style={{ color: 'var(--mcp-text-tertiary)', fontSize: 13, marginBottom: 16 }}>
                        {t('mcp_no_params')}
                      </p>
                      <Button
                        type='primary'
                        icon={<ThunderboltOutlined />}
                        className='mcp-run-btn'
                        onClick={onGoRun}
                        loading={runLoading}
                      >
                        {t('mcp_trial_run')}
                      </Button>
                    </div>
                  ) : (
                    <div className='mcp-result-empty'>
                      {t('mcp_select_tool_desc')}
                    </div>
                  )}
                </div>
              </div>

              {/* Results panel - 50% */}
              <div className='mcp-panel mcp-result-panel'>
                <div className='mcp-panel-header'>
                  <span className='mcp-panel-title'>{t('mcp_run_results')}</span>
                  {runResult && (
                    <Button
                      type='text'
                      size='small'
                      icon={<CopyOutlined />}
                      onClick={handleCopy}
                      style={{ color: 'var(--mcp-text-tertiary)' }}
                    />
                  )}
                </div>
                <div className='mcp-result-body'>
                  {runData?.[3]?.data?.success && runResult ? (
                    <JsonView
                      style={{ ...theme, width: '100%', padding: 0, overflow: 'auto', background: 'transparent' }}
                      value={runResult}
                      enableClipboard={false}
                      displayDataTypes={false}
                      objectSortKeys={false}
                    />
                  ) : runData?.[3]?.data?.err_msg ? (
                    <div className='mcp-result-error'>{runData[3].data.err_msg}</div>
                  ) : (
                    <div className='mcp-result-empty'>
                      {t('mcp_no_results')}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Spin>
  );
}
