import { getResourceV2 } from '@/client/api';
import { AppContext } from '@/contexts';
import { useRequest } from 'ahooks';
import { Button, Form, Modal, Select } from 'antd';
import { useContext, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

interface AgentModalProps {
  visible: boolean;
  onCancel: () => void;
  onAgentChange: (agents: any) => void;
  form: any;
}

function AgentModal({ visible, onCancel, onAgentChange, form }: AgentModalProps) {
  const { t } = useTranslation();
  const { appInfo } = useContext(AppContext);
  const {
    data: appListData,
    run: fetchAppListData,
    loading,
  } = useRequest(async (type: string) => await getResourceV2({ type: type }), {
    manual: true,
  });

  useEffect(() => {
    if (visible) {
      fetchAppListData('app');
    }
  }, [visible, fetchAppListData]);

  const appList = useMemo(() => {
    return appListData?.data?.data
      ?.filter(v => v.param_name === 'app_code')
      ?.flatMap(
        (item: any) =>
          item.valid_values?.map((option: any) => ({
            ...option,
            value: option.key,
            label: option.label,
            selected: true,
          })) || [],
      );
  }, [appListData]);

  const handleChange = () => {
    const agents = form.getFieldValue('agents') || [];
    const agentsList =
      agents?.map((item: any) => {
        // 查找 appInfo.resource_tool 里是否已存在 type 为 "tool" 且 name 为 item
        const existed = (appInfo?.resource_agent || []).find(
          (t: any) =>
            t.type === 'app' &&
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
        // 在 appList 中查找 value 等于 item 的数据
        const app = appList?.find((app: any) => app.value === item);
        if (app) {
          const { selected, ...rest } = app;
          return {
            type: 'app',
            name: rest.label,
            value: JSON.stringify({
              ...rest,
              value: app.key,
            }),
          };
        }
      }) || [];
    onAgentChange(agentsList);
  };

  return (
    <Modal
      title={t('agent_modal_title')}
      open={visible}
      onCancel={onCancel}
      footer={[
        <Button key='cancel' onClick={onCancel}>
          {t('agent_modal_cancel')}
        </Button>,
        <Button
          key='submit'
          type='primary'
          onClick={() => {
            handleChange();
          }}
        >
          {t('agent_modal_save')}
        </Button>,
      ]}
      width={600}
      height={400}
    >
      <div className='mt-[24px]'>
        <Form layout='horizontal' className='flex flex-col gap-4' form={form}>
          <Form.Item label={t('agent_modal_select_agent')} name='agents'>
            <Select
              mode='multiple'
              allowClear
              style={{ width: '100%' }}
              placeholder={t('agent_modal_placeholder_select_agent')}
              loading={loading}
              options={appList}
              optionFilterProp='label'
            />
          </Form.Item>
        </Form>
      </div>
    </Modal>
  );
}

export default AgentModal;
