import React, { useContext, useEffect, useState, useMemo } from "react";
import { Modal, Button, Form } from "antd";
import { getResourceV2 } from "@/client/api";
import { useRequest } from "ahooks";
import { Select } from "antd";
import { AppContext } from "@/contexts";

interface KnowledgeSelectModalProps {
  visible: boolean;
  onCancel: () => void;
  form: any;
  onKnowledgeChange: (list: any) => void;
}

function KnowledgeSelectModal({
  visible,
  onCancel,
  form,
  onKnowledgeChange
}: KnowledgeSelectModalProps) {
  const {
    data: knowledgeData,
    run: fetchKnowledgeData,
    loading,
  } = useRequest(async (type: string) => await getResourceV2({ type: type }), {
    manual: true,
  });

  const { appInfo } = useContext(AppContext);

  useEffect(() => {
    if (visible) {
      fetchKnowledgeData("knowledge");
    }
  }, [visible, fetchKnowledgeData]);

  const knowledgeList = useMemo(() => {
    return knowledgeData?.data?.data
      ?.filter((v) => v.param_name === "knowledge")
      ?.flatMap(
        (item: any) =>
          item.valid_values?.map((option: any) => ({
            ...option,
            value: option.key,
            label: option.label,
            selected: true,
          })) || []
      );
  }, [knowledgeData]);

  const knowledgeChange = (value: any, list: any) => {
    const curKnowledgeList = value?.map((val: any) => {
      const item = list.find((i: any) => i.value === val);
      if (!item) return { value: val };
      // 去掉 selected 字段
      const { selected, ...rest } = item;
      return {
        value: item?.key || val,
        ...rest
      };
    });

    const appInfo_resource_knowledge_item = appInfo?.resource_knowledge
      ? appInfo?.resource_knowledge?.[0]?.value
      : '{}';

    const _resource_knowledge = [
      {
        ...(appInfo?.resource_knowledge ? appInfo.resource_knowledge[0] : {}),
        type: "knowledge_pack",
        value: JSON.stringify({
          ...JSON.parse(appInfo_resource_knowledge_item || '{}'),
          knowledges: curKnowledgeList,
        }),
      },
    ];

    onKnowledgeChange(_resource_knowledge);
  }

  return (
    <Modal
      title="关联知识"
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
            knowledgeChange(form.getFieldValue('knowledge'), knowledgeList);
          }}
        >
          完成
        </Button>,
      ]}
      width={600}
      height={400}
    >
      <div className="mt-[24px]">
        <Form layout="horizontal" className="flex flex-col gap-4" form={form}>
          <Form.Item label="请选择知识库" name="knowledge">
            <Select
              mode="multiple"
              allowClear
              style={{ width: "100%" }}
              placeholder="请选择知识库"
              loading={loading}
              options={knowledgeList}
              optionFilterProp="label"
            />
          </Form.Item>
        </Form>
      </div>
    </Modal>
  );
}

export default KnowledgeSelectModal;
