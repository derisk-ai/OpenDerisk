import React, { useContext, useEffect, useState, useMemo } from "react";
import { Modal, Button, Form, Select, Tabs, Input, Card, Space } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { getResourceV2 } from "@/client/api";
import { useRequest } from "ahooks";
import { AppContext } from "@/contexts";

interface ToolsModalProps {
  visible: boolean;
  onCancel: () => void;
  form: any;
  onToolsChange: (tools: any[]) => void;
}

function ToolsModal({
  visible,
  onCancel,
  form,
  onToolsChange,
}: ToolsModalProps) {
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [toolKey, setToolKey] = useState<string>("tool");
  const [mcpList, setMcpList] = useState<any[]>([]);
  const { appInfo } = useContext(AppContext);
  const { resource_tool } = appInfo || {};

  const {
    data: appToolsData,
    run: fetchToolsData,
    loading,
  } = useRequest(async (type: string) => await getResourceV2({ type: type }), {
    manual: true,
  });

  useEffect(() => {
    if (visible) {
      fetchToolsData("tool");
    }
  }, [visible, fetchToolsData]);

  const appList = useMemo(() => {
    return (
      appToolsData?.data?.data
        // ?.filter((v) => v.param_name === "name")
        ?.flatMap(
          (item: any) =>
            item.valid_values?.map((option: any) => ({
              ...option,
              value: option.label,
              label: option.label,
              selected: true,
            })) || []
        )
    );
  }, [appToolsData]);

  // 过滤出 MCP 数据
  const existingMcpData = useMemo(() => {
    return resource_tool?.filter((item: { type: string; }) => item.type === "tool(mcp(sse))");
  }, []);

  useEffect(() => {
    if (visible) {
      fetchToolsData("tool");
      setMcpList(existingMcpData);
    }
  }, [visible, fetchToolsData, existingMcpData]);

  const addNewMcp = () => {
    const newMcp = {
      id: Date.now(),
      type: "tool(mcp(sse))",
      unique_id: null,
      name: "",
      value: "",
      isNew: true,
    };

    setMcpList([...(mcpList || []), newMcp]);
  };

  const removeMcp = (index: number) => {
    const newList = mcpList.filter((_, i) => i !== index);
    setMcpList(newList);
  };

  const updateMcp = (index: number, field: string, value: string) => {
    const newList = [...mcpList];
    newList[index] = { ...newList[index], [field]: value };
    setMcpList(newList);
  };

  const handleChange = () => {
    const tools = form.getFieldValue('tools') || [];
    const toolsList =
      tools?.map((item: any) => {
        // 查找 appInfo.resource_tool 里是否已存在 type 为 "tool" 且 name 为 item
        const existed = (appInfo?.resource_tool || []).find(
          (t: any) =>
            t.type === 'tool' &&
            (() => {
              try {
                const val = JSON.parse(t.value || '{}');
                return val.name === item;
              } catch {
                return false;
              }
            })(),
        );
        if (existed) {
          return existed;
        }
        const tool = appList?.find((v: any) => v.label === item);
        if (tool) {
          const { selected, ...rest } = tool;
          return {
            type: 'tool',
            name: rest.label,
            value: JSON.stringify({
              ...rest,
              value: tool.key,
            }),
          };
        }
      }) || [];
    onToolsChange([...toolsList, ...(mcpList || [])]);
  };

  return (
    <Modal
      title="关联技能"
      open={visible}
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          onClick={() => {
            onCancel();
            handleChange();
          }}
        >
          完成
        </Button>,
      ]}
      width={600}
      height={400}
    >
      <div className="gap-4">
        <Tabs
          defaultActiveKey="tool"
          tabPosition="top"
          onChange={(key) => {
            setToolKey(key);
          }}
          items={[
            { label: "工具集", key: "tool" },
            { label: "MCP", key: "mcp" },
          ]}
        />
        {toolKey === "tool" ? (
          <Form
            layout="horizontal"
            className="flex flex-col gap-4 flex-1 mt-2"
            form={form}
          >
            <Form.Item label="请选择技能" name="tools">
              <Select
                mode="multiple"
                allowClear
                style={{ width: "100%" }}
                placeholder="请选择技能"
                value={selectedTools}
                loading={loading}
                options={appList}
                onChange={setSelectedTools}
                optionFilterProp="label"
              />
            </Form.Item>
          </Form>
        ) : (
          <div className="flex flex-col gap-4 mt-2">
            {mcpList?.map((mcp, index) => (
              <Card
                key={mcp.unique_id || mcp.id}
                size="small"
                title={mcp.isNew ? `新建 MCP ${index + 1}` : mcp.name}
                extra={
                  <Button
                    type="text"
                    icon={<DeleteOutlined />}
                    onClick={() => removeMcp(index)}
                    danger
                    size="small"
                  />
                }
                className="border-gray-200"
              >
                <Form layout="vertical" size="small">
                  <Form.Item label="名称" className="mb-2">
                    <Input
                      placeholder="请输入MCP名称"
                      value={mcp.name}
                      onChange={(e) => updateMcp(index, "name", e.target.value)}
                    />
                  </Form.Item>
                  <Form.Item label="请求头" className="mb-2">
                    <Input
                      placeholder="请输入Header"
                      value={(() => {
                        try {
                          return JSON.parse(mcp.value || "{}").headers || "";
                        } catch {
                          return "";
                        }
                      })()}
                      onChange={(e) => {
                        let valueObj: { [key: string]: any } = {};
                        try {
                          valueObj = JSON.parse(mcp.value || "{}");
                        } catch {
                          valueObj = {};
                        }
                        valueObj.headers = e.target.value;
                        updateMcp(index, "value", JSON.stringify(valueObj));
                      }}
                    />
                  </Form.Item>
                  <Form.Item label="服务" className="mb-0">
                    <Input
                      placeholder="请输入MCP服务链接"
                      // value={mcp.mcp_servers || JSON.parse(mcp.value || '{}').mcp_servers}
                      // onChange={(e) => updateMcp(index, 'mcp_servers', e.target.value)}
                      value={(() => {
                        try {
                          return (
                            JSON.parse(mcp.value || "{}").mcp_servers || ""
                          );
                        } catch {
                          return "";
                        }
                      })()}
                      onChange={(e) => {
                        let valueObj: { [key: string]: any } = {};
                        try {
                          valueObj = JSON.parse(mcp.value || "{}");
                        } catch {
                          valueObj = {};
                        }
                        valueObj.mcp_servers = e.target.value;
                        updateMcp(index, "value", JSON.stringify(valueObj));
                      }}
                    />
                  </Form.Item>
                </Form>
              </Card>
            ))}

            <Button
              type="dashed"
              onClick={addNewMcp}
              icon={<PlusOutlined />}
              className="w-full h-10 border-gray-300 hover:border-blue-400 hover:text-blue-400"
            >
              添加 MCP 配置
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default ToolsModal;
