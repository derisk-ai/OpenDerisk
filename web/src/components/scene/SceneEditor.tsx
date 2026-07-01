'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Form,
  Input,
  InputNumber,
  Button,
  Select,
  message,
  Switch,
  Tooltip,
  Empty,
} from 'antd';
import {
  CloseOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { MDEditor } from './MDEditor';
import { sceneApi, SceneDefinition, TaskSpec, DeliverableSpec } from '@/client/api/scene';
import './scene-blueprint.css';

interface SceneEditorProps {
  sceneId?: string;
  onSave: () => void;
  onCancel: () => void;
}

const AVAILABLE_TOOLS = [
  { value: 'read', label: 'read', desc: '读取文件内容' },
  { value: 'write', label: 'write', desc: '写入文件内容' },
  { value: 'edit', label: 'edit', desc: '编辑文件内容' },
  { value: 'grep', label: 'grep', desc: '文本搜索' },
  { value: 'bash', label: 'bash', desc: '执行命令' },
  { value: 'webfetch', label: 'webfetch', desc: '获取网页内容' },
];

const SECTIONS = [
  { key: 'trigger', num: '01', name: '触发源', desc: 'When this scene should activate.' },
  { key: 'settings', num: '02', name: '设置', desc: 'What this scene is and who can use it.' },
  { key: 'intervene', num: '03', name: '介入', desc: 'How the agent shows up in the conversation.' },
  { key: 'tasks', num: '04', name: '任务', desc: 'What the agent does, step by step.' },
  { key: 'deliverables', num: '05', name: '产出物', desc: 'What this scene produces.' },
] as const;

type SectionKey = typeof SECTIONS[number]['key'];

export const SceneEditor: React.FC<SceneEditorProps> = ({ sceneId, onSave, onCancel }) => {
  const [form] = Form.useForm();
  const [mdContent, setMdContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeSection, setActiveSection] = useState<SectionKey>('trigger');
  const [flashSection, setFlashSection] = useState<SectionKey | null>(null);
  const sectionRefs = useRef<Record<SectionKey, HTMLElement | null>>({
    trigger: null, settings: null, intervene: null, tasks: null, deliverables: null,
  });

  useEffect(() => {
    if (sceneId) {
      loadScene(sceneId);
    } else {
      form.resetFields();
      setMdContent('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneId]);

  const loadScene = async (id: string) => {
    setLoading(true);
    try {
      const scene = await sceneApi.get(id);
      form.setFieldsValue(scene);
      setMdContent(scene.md_content || '');
    } catch {
      message.error('加载场景失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (values: any) => {
    setSaving(true);
    try {
      const data = { ...values, md_content: mdContent };
      if (sceneId) {
        await sceneApi.update(sceneId, data);
      } else {
        await sceneApi.create(data);
      }
      onSave();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  // Watch form values for chain completion state
  const watched = Form.useWatch([], form) || {};
  const completion = useMemo<Record<SectionKey, boolean>>(() => ({
    trigger:
      (watched.trigger_keywords?.length ?? 0) > 0 ||
      (watched.trigger_type && watched.trigger_type !== 'keyword'),
    settings: !!(watched.scene_name && watched.scene_id),
    intervene: !!watched.scene_role_prompt?.trim(),
    tasks: (watched.tasks?.length ?? 0) > 0,
    deliverables:
      (watched.deliverables?.length ?? 0) > 0 || mdContent.trim().length > 0,
  }), [watched, mdContent]);

  const jumpTo = (key: SectionKey) => {
    setActiveSection(key);
    setFlashSection(key);
    sectionRefs.current[key]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.setTimeout(() => setFlashSection(null), 600);
  };

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={handleSubmit}
      disabled={loading}
      initialValues={{
        trigger_priority: 5,
        trigger_keywords: [],
        trigger_type: 'keyword',
        trigger_scope: ['*'],
        scene_tools: [],
        intervention_mode: 'append',
        intervention_strategy: 'oneshot',
        tags: [],
        visibility: 'team',
        tasks: [],
        deliverables: [],
      }}
      className="bp-editor"
    >
      {/* Header */}
      <header className="bp-header">
        <p className="bp-eyebrow">{sceneId ? 'EDIT SCENE' : 'NEW SCENE'}</p>
        <h1 className="bp-title">{sceneId ? '编辑场景' : '新建场景'}</h1>
        <p className="bp-subtitle">
          {sceneId ? '修改场景的触发条件、介入方式与产出。' : '从触发源到产出物，定义一个完整的场景。'}
        </p>
      </header>

      {/* Signal chain (signature) */}
      <nav className="bp-chain" aria-label="场景结构">
        {SECTIONS.map((s, i) => (
          <React.Fragment key={s.key}>
            <button
              type="button"
              className={`bp-chain-node ${completion[s.key] ? 'is-filled' : ''} ${activeSection === s.key ? 'is-active' : ''}`}
              onClick={() => jumpTo(s.key)}
            >
              <span className="bp-chain-dot" />
              <span className="bp-chain-num">{s.num}</span>
              <span className="bp-chain-name">{s.name}</span>
            </button>
            {i < SECTIONS.length - 1 && <span className="bp-chain-connector" />}
          </React.Fragment>
        ))}
      </nav>

      {/* 01 触发源 */}
      <section
        ref={(el) => { sectionRefs.current.trigger = el; }}
        className={`bp-section ${flashSection === 'trigger' ? 'is-flash' : ''}`}
      >
        <div className="bp-section-head">
          <span className="bp-section-eyebrow">01 / TRIGGER SOURCE</span>
        </div>
        <h2 className="bp-section-title">触发源</h2>
        <p className="bp-section-desc">什么时候、在哪些地方，这个场景应该被激活。</p>

        <div className="bp-module">
          <Form.Item
            name="trigger_type"
            label="触发方式"
            tooltip="选择什么类型的信号激活这个场景"
          >
            <Select
              options={[
                { value: 'keyword', label: '关键词匹配 — 消息中出现指定词语时' },
                { value: 'intent', label: '意图识别 — 模型判断意图匹配时' },
                { value: 'manual', label: '手动调用 — 用户主动切换时' },
                { value: 'schedule', label: '定时调度 — 按计划触发' },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="trigger_keywords"
            label={
              <span>
                触发关键词{' '}
                <Tooltip title="当用户消息中出现这些词时，场景被激活。回车或逗号确认。">
                  <InfoCircleOutlined style={{ color: 'var(--bp-ink-3)' }} />
                </Tooltip>
              </span>
            }
          >
            <Select
              mode="tags"
              placeholder="输入关键词后回车，例如：故障、报警、异常"
              tokenSeparators={[',']}
              style={{ width: '100%' }}
            />
          </Form.Item>

          <Form.Item
            name="trigger_priority"
            label={
              <span>
                优先级{' '}
                <Tooltip title="当多个场景同时匹配，优先级高的胜出。1–10。">
                  <InfoCircleOutlined style={{ color: 'var(--bp-ink-3)' }} />
                </Tooltip>
              </span>
            }
          >
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="trigger_scope"
            label="触发范围"
            tooltip="这个场景可以在哪些渠道或会话中被触发。* 表示不限制。"
          >
            <Select
              mode="tags"
              placeholder={['*']}
              tokenSeparators={[',']}
              style={{ width: '100%' }}
            />
          </Form.Item>
        </div>
      </section>

      <hr className="bp-divider" />

      {/* 02 设置 */}
      <section
        ref={(el) => { sectionRefs.current.settings = el; }}
        className={`bp-section ${flashSection === 'settings' ? 'is-flash' : ''}`}
      >
        <div className="bp-section-head">
          <span className="bp-section-eyebrow">02 / SETTINGS</span>
        </div>
        <h2 className="bp-section-title">设置</h2>
        <p className="bp-section-desc">这个场景叫什么、做什么、谁能用。</p>

        <div className="bp-module">
          <Form.Item
            name="scene_id"
            label={
              <span>
                场景 ID{' '}
                <Tooltip title="唯一标识符，只能包含小写字母和下划线。创建后不可修改。">
                  <InfoCircleOutlined style={{ color: 'var(--bp-ink-3)' }} />
                </Tooltip>
              </span>
            }
            rules={[
              { required: true, message: '请输入场景 ID' },
              { pattern: /^[a-z_]+$/, message: '只能包含小写字母和下划线' },
            ]}
          >
            <Input placeholder="例如：fault_diagnosis" disabled={!!sceneId} />
          </Form.Item>

          <Form.Item
            name="scene_name"
            label="场景名称"
            rules={[{ required: true, message: '请输入场景名称' }]}
          >
            <Input placeholder="例如：故障诊断" />
          </Form.Item>

          <Form.Item name="description" label="场景描述">
            <Input.TextArea
              rows={2}
              placeholder="一两句话说明这个场景处理什么问题。"
              showCount
              maxLength={500}
            />
          </Form.Item>

          <Form.Item name="tags" label="标签" tooltip="用于在列表中过滤与分组。">
            <Select
              mode="tags"
              placeholder="例如：运维、紧急"
              tokenSeparators={[',']}
              style={{ width: '100%' }}
            />
          </Form.Item>

          <Form.Item name="visibility" label="可见性" tooltip="谁可以使用这个场景。">
            <Select
              options={[
                { value: 'private', label: '仅自己' },
                { value: 'team', label: '团队' },
                { value: 'public', label: '所有人' },
              ]}
            />
          </Form.Item>
        </div>
      </section>

      <hr className="bp-divider" />

      {/* 03 介入 */}
      <section
        ref={(el) => { sectionRefs.current.intervene = el; }}
        className={`bp-section ${flashSection === 'intervene' ? 'is-flash' : ''}`}
      >
        <div className="bp-section-head">
          <span className="bp-section-eyebrow">03 / INTERVENTION</span>
        </div>
        <h2 className="bp-section-title">介入</h2>
        <p className="bp-section-desc">Agent 以什么角色、用什么方式进入对话。</p>

        <div className="bp-module">
          <Form.Item
            name="scene_role_prompt"
            label="角色设定"
            tooltip="描述 Agent 的人设、语气与专业领域。"
          >
            <Input.TextArea
              rows={4}
              placeholder="例如：你是一位资深的故障诊断助手，擅长分析系统日志、定位根因、给出可执行的修复建议。"
              showCount
              maxLength={2000}
            />
          </Form.Item>

          <Form.Item
            name="intervention_mode"
            label="介入模式"
            tooltip="场景指令如何与基础 Prompt 组合。"
          >
            <Select
              options={[
                { value: 'append', label: '追加 — 在基础 Prompt 之后追加' },
                { value: 'prepend', label: '前置 — 在基础 Prompt 之前插入' },
                { value: 'replace', label: '替换 — 完全替换基础 Prompt' },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="intervention_strategy"
            label="介入策略"
            tooltip="Agent 介入对话的频率与方式。"
          >
            <Select
              options={[
                { value: 'oneshot', label: '一次性 — 响应一次后退出' },
                { value: 'continuous', label: '持续 — 贯穿整个会话' },
                { value: 'supervisor', label: '监督 — 在关键节点接管' },
              ]}
            />
          </Form.Item>
        </div>
      </section>

      <hr className="bp-divider" />

      {/* 04 任务 */}
      <section
        ref={(el) => { sectionRefs.current.tasks = el; }}
        className={`bp-section ${flashSection === 'tasks' ? 'is-flash' : ''}`}
      >
        <div className="bp-section-head">
          <span className="bp-section-eyebrow">04 / TASKS</span>
        </div>
        <h2 className="bp-section-title">任务</h2>
        <p className="bp-section-desc">Agent 执行的步骤。每一步可以调用一个工具。</p>

        <div className="bp-module">
          <Form.Item
            name="scene_tools"
            label={
              <span>
                允许使用的工具{' '}
                <Tooltip title="这个场景下 Agent 可以调用的工具白名单。">
                  <InfoCircleOutlined style={{ color: 'var(--bp-ink-3)' }} />
                </Tooltip>
              </span>
            }
          >
            <Select
              mode="multiple"
              placeholder="选择或输入工具名"
              tokenSeparators={[',']}
              style={{ width: '100%' }}
              optionLabelProp="label"
            >
              {AVAILABLE_TOOLS.map((tool) => (
                <Select.Option key={tool.value} value={tool.value} label={tool.label}>
                  <span className="bp-tag-mono" style={{ marginRight: 8 }}>{tool.label}</span>
                  <span style={{ color: 'var(--bp-ink-3)', fontSize: 12 }}>{tool.desc}</span>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.List name="tasks">
            {(fields, { add, remove }) => (
              <>
                {fields.length === 0 && (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="还没有任务步骤"
                    style={{ margin: '8px 0 16px' }}
                  />
                )}
                {fields.map((field, idx) => (
                  <div className="bp-row" key={field.key}>
                    <div className="bp-row-head">
                      <span className="bp-row-index">TASK · {String(idx + 1).padStart(2, '0')}</span>
                      <button
                        type="button"
                        className="bp-row-remove"
                        onClick={() => remove(field.name)}
                        aria-label="删除任务"
                      >
                        <DeleteOutlined />
                      </button>
                    </div>
                    <Form.Item
                      {...field}
                      name={[field.name, 'name']}
                      rules={[{ required: true, message: '请输入任务名称' }]}
                      label="任务名称"
                    >
                      <Input placeholder="例如：收集系统日志" />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'tool']} label="调用工具">
                      <Select
                        allowClear
                        placeholder="选择该步骤调用的工具"
                        options={AVAILABLE_TOOLS.map((t) => ({ value: t.value, label: t.label }))}
                      />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'description']} label="任务说明">
                      <Input.TextArea rows={2} placeholder="这一步要做什么、产生什么中间结果。" />
                    </Form.Item>
                    <Form.Item
                      {...field}
                      name={[field.name, 'required']}
                      valuePropName="checked"
                      label="必须完成"
                    >
                      <Switch size="small" />
                    </Form.Item>
                  </div>
                ))}
                <button
                  type="button"
                  className="bp-add-row"
                  onClick={() => add({ name: '', tool: '', description: '', required: true } as TaskSpec)}
                >
                  + 添加任务步骤
                </button>
              </>
            )}
          </Form.List>
        </div>
      </section>

      <hr className="bp-divider" />

      {/* 05 产出物 */}
      <section
        ref={(el) => { sectionRefs.current.deliverables = el; }}
        className={`bp-section ${flashSection === 'deliverables' ? 'is-flash' : ''}`}
      >
        <div className="bp-section-head">
          <span className="bp-section-eyebrow">05 / DELIVERABLES</span>
        </div>
        <h2 className="bp-section-title">产出物</h2>
        <p className="bp-section-desc">这个场景最终交回什么。报告、数据、决策、文件。</p>

        <div className="bp-module">
          <Form.List name="deliverables">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field, idx) => (
                  <div className="bp-row" key={field.key}>
                    <div className="bp-row-head">
                      <span className="bp-row-index">OUTPUT · {String(idx + 1).padStart(2, '0')}</span>
                      <button
                        type="button"
                        className="bp-row-remove"
                        onClick={() => remove(field.name)}
                        aria-label="删除产出物"
                      >
                        <DeleteOutlined />
                      </button>
                    </div>
                    <Form.Item
                      {...field}
                      name={[field.name, 'name']}
                      rules={[{ required: true, message: '请输入产出物名称' }]}
                      label="产出物名称"
                    >
                      <Input placeholder="例如：故障诊断报告" />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'type']} label="类型">
                      <Select
                        options={[
                          { value: 'report', label: '报告 — 文字结论' },
                          { value: 'data', label: '数据 — 结构化数据' },
                          { value: 'artifact', label: '产物 — 文件/工件' },
                          { value: 'decision', label: '决策 — 推荐方案' },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'format']} label="格式">
                      <Select
                        options={[
                          { value: 'markdown', label: 'Markdown' },
                          { value: 'json', label: 'JSON' },
                          { value: 'text', label: '纯文本' },
                          { value: 'file', label: '文件' },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'description']} label="说明">
                      <Input.TextArea rows={2} placeholder="这个产出物包含什么、给谁看。" />
                    </Form.Item>
                  </div>
                ))}
                <button
                  type="button"
                  className="bp-add-row"
                  onClick={() =>
                    add({ name: '', type: 'report', format: 'markdown', description: '' } as DeliverableSpec)
                  }
                >
                  + 添加产出物
                </button>
              </>
            )}
          </Form.List>
        </div>

        <div className="bp-module" style={{ marginTop: 14 }}>
          <Form.Item
            label={
              <span>
                场景定义（Markdown）{' '}
                <Tooltip title="自由形态的场景描述，将作为 System Prompt 的一部分注入。">
                  <InfoCircleOutlined style={{ color: 'var(--bp-ink-3)' }} />
                </Tooltip>
              </span>
            }
            style={{ marginBottom: 0 }}
          >
            <MDEditor
              value={mdContent}
              onChange={setMdContent}
              placeholder={`# 场景定义\n\n## 概述\n描述这个场景的目标和用途...\n\n## 处理流程\n1. 第一步：...\n2. 第二步：...\n\n## 输出格式\n定义响应格式...`}
              height={420}
            />
          </Form.Item>
        </div>
      </section>

      {/* Actions */}
      <div className="bp-actions">
        <Button size="large" icon={<CloseOutlined />} onClick={onCancel} className="bp-btn-ghost">
          取消
        </Button>
        <Button
          type="primary"
          size="large"
          onClick={() => form.submit()}
          loading={saving}
          className="bp-btn-primary"
        >
          {sceneId ? '保存修改' : '创建场景'}
        </Button>
      </div>
    </Form>
  );
};

export default SceneEditor;
