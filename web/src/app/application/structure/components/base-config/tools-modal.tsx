import React, { useContext, useEffect, useState, useMemo } from "react";
import { Modal, Button, Form, Select, Tabs } from "antd";
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
  const { appInfo } = useContext(AppContext);

  const {
    data: appToolsData,
    run: fetchToolsData,
    loading,
  } = useRequest(async (type: string) => await getResourceV2({ type: type }), {
    manual: true,
  });

  const {
    data: httpToolsData,
    run: fetchHttpToolsData,
    loading: httpLoading,
  } = useRequest(async (type: string) => await getResourceV2({ type: type }), {
    manual: true,
  });

  const {
    data: trToolsData,
    run: fetchTrToolsData,
    loading: trLoading,
  } = useRequest(async (type: string) => await getResourceV2({ type: type }), {
    manual: true,
  });

  const {
    data: localToolsData,
    run: fetchLocalToolsData,
    loading: localLoading,
  } = useRequest(async (type: string) => await getResourceV2({ type: type }), {
    manual: true,
  });

  const {
    data: mcpToolsData,
    run: fetchMcpToolsData,
    loading: mcpLoading,
  } = useRequest(async (type: string) => await getResourceV2({ type: type }), {
    manual: true,
  });

  useEffect(() => {
    if (visible) {
      fetchToolsData('tool');
      fetchLocalToolsData(toolKey);
      // fetchHttpToolsData(toolKey);
      // fetchTrToolsData(toolKey);
      fetchMcpToolsData('tool(mcp(sse))');
    }
  }, [visible, fetchToolsData, fetchHttpToolsData, fetchTrToolsData, fetchLocalToolsData, fetchMcpToolsData]);

  const appList = useMemo(() => {
    return (
      appToolsData?.data?.data
        // ?.filter((v) => v.param_name === "name")
        ?.flatMap(
          (item: any) =>
            item.valid_values?.map((option: any) => ({
              ...option,
              value: option.key,
              label: option.label,
              selected: true,
            })) || []
        )
    );
  }, [appToolsData]);

  const httpAppList = useMemo(() => {
    return (
      httpToolsData?.data?.data
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
  }, [httpToolsData]);

  const trAppList = useMemo(() => {
    return (
      trToolsData?.data?.data
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
  }, [trToolsData]);

  const localAppList = useMemo(() => {
    return (
      localToolsData?.data?.data
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
  }, [localToolsData]);

  const mcpAppList = useMemo(() => {
    return (
      mcpToolsData?.data?.data
        ?.flatMap(
          (item: any) =>
            item.valid_values?.map((option: any) => ({
              ...option,
              value: option.key,
              label: option.label,
              selected: true,
            })) || []
        )
    );
  }, [mcpToolsData]);


  const handleChange = () => {
    const allToolsList = [];
    // 处理 tool 类型
    const tools = form.getFieldValue('tools') || [];
    const toolsList = tools?.map((item: any) => {
      const existed = (appInfo?.resource_tool || []).find(
        (t: any) =>
          t.type === 'tool' &&
          (() => {
            try {
              const val = JSON.parse(t.value || '{}');
              return val.key === item;
            } catch {
              return false;
            }
          })(),
      );
      if (existed) {
        return existed;
      }
      const tool = appList?.find((v: any) => v.key === item);
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
    }).filter(Boolean) || [];
    
    // 处理 tool(http) 类型
    const httpTools = form.getFieldValue('tool(http)') || [];
    const httpToolsList = httpTools?.map((item: any) => {
      const existed = (appInfo?.resource_tool || []).find(
        (t: any) =>
          t.type === 'tool(http)' &&
          (() => {
            try {
              const val = JSON.parse(t.value || '{}');
              return val.key === item;
            } catch {
              return false;
            }
          })(),
      );
      if (existed) {
        return existed;
      }
      const tool = httpAppList?.find((v: any) => v.key === item);
      if (tool) {
        const { selected, ...rest } = tool;
        return {
          type: 'tool(http)',
          name: rest.label,
          value: JSON.stringify({
            ...rest,
            value: tool.key,
          }),
        };
      }
    }).filter(Boolean) || [];
    
    // 处理 tool(tr) 类型
    const trTools = form.getFieldValue('tool(tr)') || [];
    const trToolsList = trTools?.map((item: any) => {
      const existed = (appInfo?.resource_tool || []).find(
        (t: any) =>
          t.type === 'tool(tr)' &&
          (() => {
            try {
              const val = JSON.parse(t.value || '{}');
              return val.key === item;
            } catch {
              return false;
            }
          })(),
      );
      if (existed) {
        return existed;
      }
      const tool = trAppList?.find((v: any) => v.key === item);
      if (tool) {
        const { selected, ...rest } = tool;
        return {
          type: 'tool(tr)',
          name: rest.label,
          value: JSON.stringify({
            ...rest,
            value: tool.key,
          }),
        };
      }
    }).filter(Boolean) || [];

    // 处理 tool(local) 类型
    const localTools = form.getFieldValue('tool(local)') || [];
    const localToolsList = localTools?.map((item: any) => {
      const existed = (appInfo?.resource_tool || []).find(
        (t: any) =>
          t.type === 'tool(local)' &&
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
      const tool = localAppList?.find((v: any) => v.label === item);
      if (tool) {
        const { selected, ...rest } = tool;
        return {
          type: 'tool(local)',
          name: rest.label,
          value: JSON.stringify({
            ...rest,
            value: tool.key,
          }),
        };
      }
    }).filter(Boolean) || [];

    // 处理 tool(mcp) 类型
    const mcpTools = form.getFieldValue('tool(mcp(sse))') || [];
    const mcpToolsList = mcpTools?.map((item: any) => {
      const existed = (appInfo?.resource_tool || []).find(
        (t: any) =>
          t.type === 'tool(mcp(sse))' &&
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
      const tool = mcpAppList?.find((v: any) => v.key === item);
      if (tool) {
        const { selected, ...rest } = tool;
        return {
          type: 'tool(mcp(sse))',
          name: rest.label,
          value: JSON.stringify({
            ...rest,
            value: tool.key,
          }),
        };
      }
    }).filter(Boolean) || [];
    
    // 合并所有工具
    allToolsList.push(...toolsList, ...httpToolsList, ...trToolsList, ...localToolsList, ...mcpToolsList);
    
    onToolsChange([...allToolsList]);
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
          activeKey={toolKey}
          tabPosition="top"
          onChange={(key) => {
            setToolKey(key);
          }}
          items={[
            { 
              label: "工具集", 
              key: "tool",
              children: (
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
              )
            },
            { 
              label: "MCP", 
              key: "tool(mcp(sse))",
              children: (
                <Form
                  layout="horizontal"
                  className="flex flex-col gap-4 flex-1 mt-2"
                  form={form}
                >
                  <Form.Item label="请选择MCP技能" name="tool(mcp(sse))">
                    <Select
                      mode="multiple"
                      allowClear
                      style={{ width: "100%" }}
                      placeholder="请选择MCP技能"
                      value={selectedTools}
                      loading={mcpLoading}
                      options={mcpAppList}
                      onChange={setSelectedTools}
                      optionFilterProp="label"
                    />
                  </Form.Item>
                </Form>
              )
            },
//             {
//               label: "API",
//               key: "tool(http)",
//               children: (
//                 <Form
//                   layout="horizontal"
//                   className="flex flex-col gap-4 flex-1 mt-2"
//                   form={form}
//                 >
//                   <Form.Item label="请选择API技能" name="tool(http)">
//                     <Select
//                       mode="multiple"
//                       allowClear
//                       style={{ width: "100%" }}
//                       placeholder="请选择API技能"
//                       value={selectedTools}
//                       loading={httpLoading}
//                       options={httpAppList}
//                       onChange={setSelectedTools}
//                       optionFilterProp="label"
//                     />
//                   </Form.Item>
//                 </Form>
//               )
//             },
//             {
//               label: "TR",
//               key: "tool(tr)",
//               children: (
//                 <Form
//                   layout="horizontal"
//                   className="flex flex-col gap-4 flex-1 mt-2"
//                   form={form}
//                 >
//                   <Form.Item label="请选择TR技能" name="tool(tr)">
//                     <Select
//                       mode="multiple"
//                       allowClear
//                       style={{ width: "100%" }}
//                       placeholder="请选择TR技能"
//                       value={selectedTools}
//                       loading={trLoading}
//                       options={trAppList}
//                       onChange={setSelectedTools}
//                       optionFilterProp="label"
//                     />
//                   </Form.Item>
//                 </Form>
//               )
//             },
            { 
              label: "Local", 
              key: "tool(local)",
              children: (
                <Form
                  layout="horizontal"
                  className="flex flex-col gap-4 flex-1 mt-2"
                  form={form}
                >
                  <Form.Item label="请选择Local技能" name="tool(local)">
                    <Select
                      mode="multiple"
                      allowClear
                      style={{ width: "100%" }}
                      placeholder="请选择Local技能"
                      value={selectedTools}
                      loading={localLoading}
                      options={localAppList}
                      onChange={setSelectedTools}
                      optionFilterProp="label"
                    />
                  </Form.Item>
                </Form>
              )
            },
            
          ]}
        />
      </div>
    </Modal>
  );
}

export default ToolsModal;
