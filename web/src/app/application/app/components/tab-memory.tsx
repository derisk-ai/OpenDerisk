'use client';
// TODO: rewire to new knowledge-vault page — getSpaceList removed from @/client/api.
import { apiInterceptors } from '@/client/api';
import { disableAppMemory, enableAppMemory } from '@/client/api/app';
import { AppContext } from '@/contexts';
import { notification } from 'antd';
import {
  BulbOutlined,
  CaretDownOutlined,
  CaretRightOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  SwapOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
// TODO: rewire to new knowledge-vault page — useRequest removed (was used for getSpaceList).
// import { useRequest } from 'ahooks';
import {
  Button,
  InputNumber,
  message,
  Select,
  Spin,
  Switch,
  Tooltip,
} from 'antd';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface MemoryConfig {
  auto_memory: boolean;
  enable_kg: boolean;
  top_k: number;
  reflection_interval: number;
}

const DEFAULT_CONFIG: MemoryConfig = {
  auto_memory: true,
  enable_kg: false,
  top_k: 5,
  reflection_interval: 10,
};

export default function TabMemory() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp, refreshAppInfo } = useContext(AppContext);
  const [switching, setSwitching] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [draft, setDraft] = useState<MemoryConfig | null>(null);
  const [hookDraft, setHookDraft] = useState<Record<string, any>[] | null>(null);

  // TODO: rewire to new knowledge-vault page — getSpaceList removed; spaceData stays empty until rewired.
  // Fetch all knowledge spaces
  const spaceData: any[] = [];
  const loading = false;
  const refresh = async () => {};

  // Filter Memory-type spaces
  const memorySpaces = useMemo(() => {
    if (!spaceData) return [];
    return spaceData
      .filter((space: any) => space.vector_type === 'Memory')
      .map((space: any) => ({
        value: space.knowledge_id || space.id,
        label: space.name,
        name: space.name,
        description: space.desc,
      }));
  }, [spaceData]);

  // Parse current resource_memory
  const parsed = useMemo(() => {
    const value = appInfo?.resource_memory?.[0]?.value;
    if (!value) return null;
    try {
      return JSON.parse(value);
    } catch {
      return null;
    }
  }, [appInfo?.resource_memory]);

  const enabled = useMemo(() => {
    return Boolean(parsed?.memories && parsed.memories.length > 0);
  }, [parsed]);

  const currentMemory = parsed?.memories?.[0];

  const currentConfig: MemoryConfig = useMemo(
    () => ({
      auto_memory: parsed?.auto_memory ?? DEFAULT_CONFIG.auto_memory,
      enable_kg: parsed?.enable_kg ?? DEFAULT_CONFIG.enable_kg,
      top_k: parsed?.top_k ?? DEFAULT_CONFIG.top_k,
      reflection_interval: parsed?.reflection_interval ?? DEFAULT_CONFIG.reflection_interval,
    }),
    [parsed],
  );

  // The draft is what's currently being edited; falls back to currentConfig
  const editConfig = draft ?? currentConfig;
  const dirty = draft !== null;

  const buildResourceMemory = (memories: any[], config: MemoryConfig) => {
    return [
      {
        ...(appInfo?.resource_memory?.[0] || {}),
        type: 'memory',
        name: 'memory',
        value: JSON.stringify({
          memories,
          auto_memory: config.auto_memory,
          enable_kg: config.enable_kg,
          top_k: config.top_k,
          reflection_interval: config.reflection_interval,
        }),
      },
    ];
  };

  const handleToggleMemory = async (on: boolean) => {
    if (!appInfo?.app_code) return;
    setSwitching(true);
    try {
      const [err, data, raw] = on
        ? await apiInterceptors(enableAppMemory(appInfo.app_code), notification)
        : await apiInterceptors(disableAppMemory(appInfo.app_code), notification);
      // eslint-disable-next-line no-console
      console.log('[tab-memory] toggle', on ? 'enable' : 'disable', 'err:', err, 'data:', data, 'raw:', raw);
      if (err) {
        console.error('[tab-memory] toggle failed:', err, 'raw response:', raw);
        message.error(
          `${on ? 'enable' : 'disable'} memory failed: ${err?.message || 'unknown'}`,
        );
        return;
      }
      message.success(on ? t('memory_enable_memory') : `${t('memory_enable_memory')} · off`);
      setDraft(null);
      refreshAppInfo?.();
    } catch (e) {
      console.error('[tab-memory] toggle exception:', e);
      message.error(`toggle memory exception: ${(e as Error)?.message || e}`);
    } finally {
      setSwitching(false);
    }
  };

  // Save advanced config changes via the standard edit flow
  const handleSaveAdvanced = async () => {
    if (!draft || !appInfo) return;
    const memories = parsed?.memories || [];
    if (memories.length === 0) {
      message.warning(t('memory_no_space_bound'));
      return;
    }
    await fetchUpdateApp({
      ...appInfo,
      resource_memory: buildResourceMemory(memories, draft),
    });
    setDraft(null);
  };

  const handleConfigChange = (key: keyof MemoryConfig, value: any) => {
    setDraft({ ...(draft ?? currentConfig), [key]: value });
  };

  const handleChangeSpace = async (memoryId: string) => {
    if (!appInfo) return;
    const space = memorySpaces.find((s: any) => s.value === memoryId);
    const newMemories = [
      {
        memory_id: memoryId,
        memory_name: space?.name || '',
      },
    ];
    await fetchUpdateApp({
      ...appInfo,
      resource_memory: buildResourceMemory(newMemories, currentConfig),
    });
  };

  // ----- Memory tier hooks (visible + editable) -----
  const TIER_LABEL_KEYS: Record<number, string> = {
    0: 'memory_hook_tier0',
    1: 'memory_hook_tier1',
    2: 'memory_hook_tier2',
    3: 'memory_hook_tier3',
  };

  // Hooks persisted in team_context.hook_config.hooks; filter the 4 memory tiers
  // and sort by tier number (parsed from name suffix: memory_tier{N}_*).
  const memoryHooks = useMemo(() => {
    const tc = appInfo?.team_context as any;
    const hookConfig = tc?.hook_config;
    const hooks: any[] = hookConfig?.hooks || [];
    // eslint-disable-next-line no-console
    console.log('[tab-memory] team_context:', tc, 'hook_config:', hookConfig, 'all hooks count:', hooks.length, 'memory hooks:', hooks.filter((h: any) => h?.name?.startsWith('memory_tier')));
    return hooks
      .filter((h: any) => typeof h?.name === 'string' && h.name.startsWith('memory_tier'))
      .map((h: any) => {
        const m = /^memory_tier(\d+)_/.exec(h.name);
        return { ...h, _tier: m ? Number(m[1]) : 99 };
      })
      .sort((a: any, b: any) => a._tier - b._tier);
  }, [appInfo?.team_context]);

  const hookEditList = hookDraft ?? memoryHooks;
  const hookDirty = hookDraft !== null;

  const handleHookFieldChange = (name: string, key: string, value: any) => {
    const next = (hookDraft ?? memoryHooks).map((h: any) =>
      h.name === name ? { ...h, [key]: value } : h,
    );
    // Keep trigger.every_n_turns in sync if present.
    setHookDraft(next);
  };

  const handleSaveHooks = async () => {
    if (!hookDraft || !appInfo) return;
    const teamContext = { ...((appInfo.team_context as any) || {}) };
    const hookConfig = { ...(teamContext.hook_config || {}) };
    const otherHooks = (hookConfig.hooks || []).filter(
      (h: any) => !(typeof h?.name === 'string' && h.name.startsWith('memory_tier')),
    );
    // Strip the _tier helper field before persisting.
    const cleanedMemoryHooks = hookDraft.map(({ _tier, ...rest }: any) => rest);
    hookConfig.hooks = [...otherHooks, ...cleanedMemoryHooks];
    hookConfig.enabled = true;
    teamContext.hook_config = hookConfig;
    await fetchUpdateApp({
      ...appInfo,
      team_context: teamContext,
    });
    setHookDraft(null);
  };

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4 custom-scrollbar">
      {/* Top: enable switch */}
      <div className="flex items-center justify-between p-4 rounded-xl border border-gray-100 bg-white">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-violet-100 flex items-center justify-center flex-shrink-0">
            <BulbOutlined className="text-violet-500" />
          </div>
          <div>
            <div className="text-[14px] font-medium text-gray-800">
              {t('memory_enable_memory')}
            </div>
            <div className="text-[12px] text-gray-400 mt-0.5">
              {t('memory_enable_memory_desc')}
            </div>
          </div>
        </div>
        <Spin spinning={switching} size="small">
          <Switch
            checked={enabled}
            onChange={handleToggleMemory}
            disabled={switching}
          />
        </Spin>
      </div>

      {/* Current space */}
      {enabled && (
        <div className="p-4 rounded-xl border border-gray-100 bg-white">
          <div className="flex items-center gap-3">
            <NodeIndexOutlined className="text-violet-500" />
            <div className="flex-1 min-w-0">
              <div className="text-[12px] text-gray-400">
                {t('memory_current_space')}
              </div>
              <div className="text-[14px] font-medium text-gray-800 truncate mt-0.5">
                {currentMemory?.memory_name || t('memory_no_space_bound')}
              </div>
            </div>
            <Tooltip title={t('memory_change_space')}>
              <Select
                size="small"
                value={currentMemory?.memory_id}
                onChange={handleChangeSpace}
                className="min-w-[180px]"
                placeholder={t('memory_change_space')}
                showSearch
                optionFilterProp="label"
                options={memorySpaces}
                suffixIcon={<SwapOutlined />}
              />
            </Tooltip>
            <Tooltip title={t('builder_refresh')}>
              <button
                onClick={refresh}
                className="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200/80 bg-white hover:bg-gray-50 text-gray-400 hover:text-gray-600 transition-all flex-shrink-0"
              >
                <ReloadOutlined className={`text-xs ${loading ? 'animate-spin' : ''}`} />
              </button>
            </Tooltip>
          </div>
        </div>
      )}

      {/* Advanced settings */}
      {enabled && (
        <div className="rounded-xl border border-gray-100 bg-white overflow-hidden">
          <button
            onClick={() => setAdvancedOpen(!advancedOpen)}
            className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50/50 transition-colors"
          >
            <span className="text-[13px] font-medium text-gray-700">
              {t('memory_advanced_settings')}
            </span>
            {advancedOpen ? (
              <CaretDownOutlined className="text-gray-400 text-xs" />
            ) : (
              <CaretRightOutlined className="text-gray-400 text-xs" />
            )}
          </button>
          {advancedOpen && (
            <div className="px-4 pb-4 pt-1 border-t border-gray-50">
              <div className="grid grid-cols-2 gap-x-6 gap-y-3 mt-3">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-gray-600">
                    {t('memory_auto_memory')}
                  </span>
                  <Switch
                    size="small"
                    checked={editConfig.auto_memory}
                    onChange={(v) => handleConfigChange('auto_memory', v)}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-gray-600">
                    {t('memory_enable_kg')}
                  </span>
                  <Switch
                    size="small"
                    checked={editConfig.enable_kg}
                    onChange={(v) => handleConfigChange('enable_kg', v)}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-gray-600">
                    {t('memory_top_k')}
                  </span>
                  <InputNumber
                    size="small"
                    min={1}
                    max={20}
                    value={editConfig.top_k}
                    onChange={(v) => handleConfigChange('top_k', v || 5)}
                    className="w-20"
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-gray-600">
                    {t('memory_reflection_interval')}
                  </span>
                  <InputNumber
                    size="small"
                    min={1}
                    max={100}
                    value={editConfig.reflection_interval}
                    onChange={(v) => handleConfigChange('reflection_interval', v || 10)}
                    className="w-20"
                  />
                </div>
              </div>
              {dirty && (
                <div className="flex justify-end gap-2 mt-4">
                  <Button size="small" onClick={() => setDraft(null)}>
                    Cancel
                  </Button>
                  <Button size="small" type="primary" onClick={handleSaveAdvanced}>
                    Save
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Memory tier hooks (visible + editable) */}
      {enabled && memoryHooks.length > 0 && (
        <div className="rounded-xl border border-gray-100 bg-white overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-50 flex items-start gap-2">
            <ThunderboltOutlined className="text-violet-500 mt-0.5" />
            <div>
              <div className="text-[13px] font-medium text-gray-700">
                {t('memory_hooks_section')}
              </div>
              <div className="text-[11px] text-gray-400 mt-0.5">
                {t('memory_hooks_section_desc')}
              </div>
            </div>
          </div>
          <div className="divide-y divide-gray-50">
            {hookEditList.map((hook: any) => {
              const tier = hook._tier ?? 99;
              const isTier3 = tier === 3;
              const enabledVal = hook.enabled !== false;
              const everyN =
                hook.trigger?.every_n_turns ?? (isTier3 ? null : 1);
              return (
                <div
                  key={hook.name}
                  className="px-4 py-3 flex items-center gap-4"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium text-gray-700">
                      {TIER_LABEL_KEYS[tier] ? t(TIER_LABEL_KEYS[tier] as any) : `Tier ${tier}`}
                    </div>
                    <div className="text-[11px] text-gray-400 mt-0.5 truncate">
                      {hook.description || hook.name}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-[12px] text-gray-500">
                    <span>{t('memory_hook_every_n')}</span>
                    {isTier3 ? (
                      <span className="text-gray-400">
                        {t('memory_hook_session_end')}
                      </span>
                    ) : (
                      <InputNumber
                        size="small"
                        min={1}
                        max={100}
                        value={everyN}
                        onChange={(v) => {
                          const next = (hookDraft ?? memoryHooks).map(
                            (h: any) =>
                              h.name === hook.name
                                ? {
                                    ...h,
                                    trigger: {
                                      ...(h.trigger || {}),
                                      every_n_turns: v || 1,
                                    },
                                  }
                                : h,
                          );
                          setHookDraft(next);
                        }}
                        className="w-20"
                      />
                    )}
                  </div>
                  <Switch
                    size="small"
                    checked={enabledVal}
                    onChange={(v) => handleHookFieldChange(hook.name, 'enabled', v)}
                  />
                </div>
              );
            })}
          </div>
          {hookDirty && (
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-50">
              <Button size="small" onClick={() => setHookDraft(null)}>
                Cancel
              </Button>
              <Button size="small" type="primary" onClick={handleSaveHooks}>
                {t('memory_hook_save')}
              </Button>
            </div>
          )}
        </div>
      )}

      {!enabled && (
        <div className="text-center py-8 text-gray-300 text-xs">
          {t('memory_enable_memory_desc')}
        </div>
      )}
    </div>
  );
}
