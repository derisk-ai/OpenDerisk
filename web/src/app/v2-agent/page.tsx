'use client';
import React, { useState, useEffect } from 'react';
import { Layout, Card, Select, Typography, Row, Col, Divider, Tag, Tabs, message } from 'antd';
import { RobotOutlined, ThunderboltOutlined, AppstoreOutlined } from '@ant-design/icons';
import V2Chat from '@/components/v2-chat';
import { sceneApi, SceneDefinition } from '@/client/api/scene';

const { Content } = Layout;
const { Title, Text } = Typography;

const AGENT_OPTIONS = [
  { 
    value: 'react_reasoning', 
    label: '智能推理Agent（推荐）', 
    description: '通用智能Agent，支持复杂任务推理、末日循环检测',
    type: 'basic',
    recommended: true
  },
  { 
    value: 'coding', 
    label: '编程开发Agent', 
    description: '专注代码开发，支持代码库探索、智能定位',
    type: 'basic'
  },
  { 
    value: 'simple_chat', 
    label: '简单对话Agent', 
    description: '基础对话Agent，无工具调用',
    type: 'basic'
  },
];

export default function V2AgentPage() {
  const [selectedAgent, setSelectedAgent] = useState('react_reasoning');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [activeScene, setActiveScene] = useState<string | null>(null);
  const [availableScenes, setAvailableScenes] = useState<SceneDefinition[]>([]);
  const [loading, setLoading] = useState(false);

  const currentAgent = AGENT_OPTIONS.find((a) => a.value === selectedAgent);
  const isSceneAware = currentAgent?.type === 'scene_aware';

  // 加载可用场景
  useEffect(() => {
    loadScenes();
  }, []);

  const loadScenes = async () => {
    setLoading(true);
    try {
      const scenes = await sceneApi.list();
      setAvailableScenes(scenes);
    } catch (error) {
      console.error('Failed to load scenes:', error);
    } finally {
      setLoading(false);
    }
  };

  // 当 Agent 改变时，重置当前场景
  useEffect(() => {
    setActiveScene(null);
  }, [selectedAgent]);

  // 获取当前 Agent 关联的场景
  const getAgentScenes = () => {
    if (!currentAgent?.scenes) return [];
    return availableScenes.filter(scene => 
      currentAgent.scenes?.includes(scene.scene_id)
    );
  };

  const agentScenes = getAgentScenes();

  const handleAgentChange = (value: string) => {
    setSelectedAgent(value);
    setActiveScene(null);
  };

  const handleSceneChange = (sceneId: string) => {
    setActiveScene(sceneId);
    message.success(`场景已切换至: ${sceneId}`);
  };

  return (
    <Content style={{ minHeight: '100vh', padding: 24, background: '#f5f5f5' }}>
      <Row justify="center">
        <Col xs={24} lg={18} xl={14}>
          <Card>
            {/* 头部区域 */}
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
              <RobotOutlined style={{ fontSize: 32, color: '#1890ff', marginRight: 16 }} />
              <div style={{ flex: 1 }}>
                <Title level={3} style={{ margin: 0 }}>Core_v2 Agent</Title>
                <Text type="secondary">Powered by new Core_v2 architecture</Text>
              </div>
              <Select
                value={selectedAgent}
                onChange={handleAgentChange}
                style={{ width: 280 }}
                optionLabelProp="label"
              >
                <Select.OptGroup label="基础 Agent">
                  {AGENT_OPTIONS.filter(a => a.type === 'basic').map(agent => (
                    <Select.Option 
                      key={agent.value} 
                      value={agent.value}
                      label={agent.label}
                    >
                      <div style={{ padding: '4px 0' }}>
                        <div style={{ fontWeight: 500 }}>{agent.label}</div>
                        <div style={{ fontSize: 12, color: '#666' }}>{agent.description}</div>
                      </div>
                    </Select.Option>
                  ))}
                </Select.OptGroup>
                <Select.OptGroup label="场景感知 Agent">
                  {AGENT_OPTIONS.filter(a => a.type === 'scene_aware').map(agent => (
                    <Select.Option 
                      key={agent.value} 
                      value={agent.value}
                      label={agent.label}
                    >
                      <div style={{ padding: '4px 0' }}>
                        <div style={{ fontWeight: 500 }}>
                          {agent.label}
                          <Tag color="purple" style={{ marginLeft: 8, fontSize: 10 }}>场景感知</Tag>
                        </div>
                        <div style={{ fontSize: 12, color: '#666' }}>{agent.description}</div>
                        {agent.scenes && (
                          <div style={{ marginTop: 4 }}>
                            {agent.scenes.map(sceneId => {
                              const scene = availableScenes.find(s => s.scene_id === sceneId);
                              return (
                                <Tag key={sceneId} size="small" style={{ fontSize: 10 }}>
                                  {scene?.scene_name || sceneId}
                                </Tag>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </Select.Option>
                  ))}
                </Select.OptGroup>
              </Select>
            </div>

            {/* Agent 信息 */}
            {currentAgent && (
              <div style={{ marginBottom: 16, padding: 16, background: '#f6ffed', borderRadius: 8, border: '1px solid #b7eb8f' }}>
                <Text strong style={{ fontSize: 16 }}>{currentAgent.label}</Text>
                <Text type="secondary" style={{ marginLeft: 8 }}>{currentAgent.description}</Text>
                {isSceneAware && (
                  <div style={{ marginTop: 8 }}>
                    <Tag color="purple">
                      <AppstoreOutlined /> 场景感知 Agent
                    </Tag>
                    <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                      支持自动场景检测和切换
                    </Text>
                  </div>
                )}
              </div>
            )}

            {/* 场景选择器（仅场景感知 Agent 显示） */}
            {isSceneAware && (
              <div style={{ marginBottom: 16, padding: 16, background: '#f9f0ff', borderRadius: 8, border: '1px solid #d3adf7' }}>
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
                  <ThunderboltOutlined style={{ color: '#722ed1', marginRight: 8 }} />
                  <Text strong style={{ color: '#722ed1' }}>工作场景</Text>
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                    选择或切换当前工作场景
                  </Text>
                </div>
                
                {agentScenes.length > 0 ? (
                  <Tabs
                    activeKey={activeScene || agentScenes[0]?.scene_id}
                    onChange={handleSceneChange}
                    type="card"
                    size="small"
                  >
                    {agentScenes.map(scene => (
                      <Tabs.TabPane
                        key={scene.scene_id}
                        tab={
                          <span>
                            {scene.scene_name}
                            <Tag color="blue" style={{ marginLeft: 4, fontSize: 10 }}>
                              优先级 {scene.trigger_priority}
                            </Tag>
                          </span>
                        }
                      >
                        <div style={{ padding: 12, background: '#fff', borderRadius: 4 }}>
                          <Text strong>场景描述：</Text>
                          <Text>{scene.description || '暂无描述'}</Text>
                          <div style={{ marginTop: 8 }}>
                            <Text strong>触发关键词：</Text>
                            {scene.trigger_keywords.map(keyword => (
                              <Tag key={keyword} size="small" style={{ marginRight: 4 }}>
                                {keyword}
                              </Tag>
                            ))}
                          </div>
                          <div style={{ marginTop: 8 }}>
                            <Text strong>可用工具：</Text>
                            {scene.scene_tools.map(tool => (
                              <Tag key={tool} color="blue" size="small" style={{ marginRight: 4 }}>
                                {tool}
                              </Tag>
                            ))}
                          </div>
                        </div>
                      </Tabs.TabPane>
                    ))}
                  </Tabs>
                ) : (
                  <Text type="secondary">
                    暂无可用的工作场景，请在场景管理页面创建场景
                  </Text>
                )}
              </div>
            )}

            <Divider />
            
            {/* 聊天组件 */}
            <V2Chat
              key={`${selectedAgent}-${activeScene}`}
              agentName={selectedAgent}
              sceneId={activeScene}
              height={500}
              onSessionChange={setSessionId}
            />
            
            {sessionId && (
              <div style={{ marginTop: 8, textAlign: 'right' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Session: {sessionId.slice(0, 8)}...
                  {activeScene && ` | 当前场景: ${activeScene}`}
                </Text>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </Content>
  );
}
