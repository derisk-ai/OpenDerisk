'use client';
import { apiInterceptors, getAppList, newDialogue } from '@/client/api';
import { STORAGE_INIT_MESSAGE_KET } from '@/utils/constants/storage';
import {
  AppstoreOutlined,
  ArrowUpOutlined,
  BulbOutlined,
  CodeOutlined,
  DesktopOutlined,
  DownOutlined,
  FileTextOutlined,
  FundProjectionScreenOutlined,
  PaperClipOutlined,
  PlusOutlined,
  ToolOutlined,
  ApiOutlined
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import {
  Badge,
  Button,
  Dropdown,
  Input,
  MenuProps,
  Popover,
  Typography,
  Upload,
  UploadProps,
} from 'antd';
import cls from 'classnames';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ConnectorsModal } from '@/components/chat/connectors-modal';
import { IApp } from '@/types/app';

const { Title, Text } = Typography;

const FilePreview = ({ file, onRemove }: { file: File; onRemove: () => void }) => {
  const [preview, setPreview] = useState<string>('');

  useEffect(() => {
    if (file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file);
      setPreview(url);
      return () => URL.revokeObjectURL(url);
    }
  }, [file]);

  return (
    <div className="relative group w-10 h-10 rounded-lg border border-gray-100 dark:border-gray-700 overflow-hidden flex-shrink-0 bg-white dark:bg-[#1F1F1F]">
      {file.type.startsWith('image/') ? (
        <img src={preview} alt={file.name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex flex-col items-center justify-center bg-gray-50 dark:bg-gray-800 gap-1">
          <FileTextOutlined className="text-gray-400 text-xl" />
          <span className="text-[10px] text-gray-400 truncate w-full text-center px-1">
            {file.name}
          </span>
        </div>
      )}
      <div
        className="absolute top-1 right-1 w-5 h-5 bg-black/50 hover:bg-red-500 rounded-full flex items-center justify-center cursor-pointer transition-all opacity-0 group-hover:opacity-100 backdrop-blur-sm"
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
      >
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="white"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </div>
    </div>
  );
};

export default function HomeChat() {
  const router = useRouter();
  const { t } = useTranslation();
  const [userInput, setUserInput] = useState<string>('');
  const [isFocus, setIsFocus] = useState<boolean>(false);
  const [fileList, setFileList] = useState<any[]>([]);
  const [isConnectorsModalOpen, setIsConnectorsModalOpen] = useState(false);
  const [connectorsModalTab, setConnectorsModalTab] = useState<'mcp' | 'local' | 'skill'>('mcp');
  const [selectedApp, setSelectedApp] = useState<IApp | null>(null);
  const [appList, setAppList] = useState<IApp[]>([]);

  // 从 URL 参数中获取 app_code
  // Use useEffect to access URL search params safely on client side
  useEffect(() => {
    // Basic way to get query params without using useSearchParams which might cause hydration issues
    const urlParams = new URLSearchParams(window.location.search);
    const appCode = urlParams.get('app_code');
    
    if (appCode && appList.length > 0) {
      const app = appList.find(a => a.app_code === appCode);
      if (app) {
        setSelectedApp(app);
      }
    }
  }, [appList]);

  const { run: fetchAppList } = useRequest(
    async () => {
      const [_, data] = await apiInterceptors(
        getAppList({
          page: 1,
          page_size: 100,
          published: true,
        }),
      );
      return data;
    },
    {
      onSuccess: (data) => {
        if (data?.app_list) {
          setAppList(data.app_list);
          const defaultApp =
            data.app_list.find((app) => app.app_code === 'chat_normal') || data.app_list[0];
          setSelectedApp(defaultApp);
        }
      },
    },
  );

  const onSubmit = async () => {
    if (!userInput.trim() && fileList.length === 0) return;

    // Here we would typically upload files first or send them with the message
    // For now, we'll just create the dialogue
    const appCode = selectedApp?.app_code || 'chat_normal';
    const [, res] = await apiInterceptors(newDialogue({ app_code: appCode }));
    if (res) {
      localStorage.setItem(
        STORAGE_INIT_MESSAGE_KET,
        JSON.stringify({
          id: res.conv_uid,
          message: userInput,
          files: fileList, // We might need to handle this in the chat page
        }),
      );
      router.push(`/chat/?app_code=${appCode}&conv_uid=${res.conv_uid}`);
    }
    setUserInput('');
    setFileList([]);
  };

  const uploadProps: UploadProps = {
    onRemove: (file) => {
      const index = fileList.indexOf(file);
      const newFileList = fileList.slice();
      newFileList.splice(index, 1);
      setFileList(newFileList);
    },
    beforeUpload: (file) => {
      setFileList([...fileList, file]);
      return false;
    },
    fileList,
  };

  const QuickActionButton = ({ icon, text }: { icon: React.ReactNode; text: string }) => (
    <div className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-[#232734] border border-gray-100 dark:border-gray-700 rounded-full shadow-sm hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer transition-all">
      <span className="text-gray-500">{icon}</span>
      <span className="text-sm text-gray-700 dark:text-gray-300">{text}</span>
    </div>
  );

  const openConnectorsModal = (tab: 'mcp' | 'local' | 'skill') => {
    setConnectorsModalTab(tab);
    setIsConnectorsModalOpen(true);
  };

  const appMenuProps: MenuProps = {
    items: appList.map((app) => ({
      key: app.app_code,
      label: (
        <div className="flex items-center gap-2" onClick={() => setSelectedApp(app)}>
          <span className="text-base">
            {app.icon ? <img src={app.icon} className="w-4 h-4" /> : '🤖'}
          </span>
          <span>{app.app_name}</span>
        </div>
      ),
    })),
  };

  const plusMenuContent = (
    <div className="flex flex-col gap-1 w-48 p-1">
      <Upload {...uploadProps} showUploadList={false} className="w-full">
        <div className="flex items-center gap-3 px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg cursor-pointer transition-colors text-gray-700 dark:text-gray-200 w-full">
          <FileTextOutlined className="text-lg" />
          <span className="text-sm">从本地文件添加</span>
        </div>
      </Upload>

      <div
        className="flex items-center gap-3 px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg cursor-pointer transition-colors text-gray-700 dark:text-gray-200"
        onClick={() => openConnectorsModal('skill')}
      >
        <AppstoreOutlined className="text-lg" />
        <span className="text-sm">使用技能</span>
      </div>

      <div
        className="flex items-center gap-3 px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg cursor-pointer transition-colors text-gray-700 dark:text-gray-200"
        onClick={() => openConnectorsModal('local')}
      >
        <ToolOutlined className="text-lg" />
        <span className="text-sm">使用工具</span>
      </div>

      <div className="h-[1px] bg-gray-100 dark:bg-gray-800 my-1 mx-2" />

      <div
        className="flex items-center gap-3 px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg cursor-pointer transition-colors text-gray-700 dark:text-gray-200"
        onClick={() => openConnectorsModal('mcp')}
      >
        <ApiOutlined className="text-lg" />
        <span className="text-sm">更多</span>
      </div>
    </div>
  );

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (items) {
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) {
            setFileList((prev) => [...prev, file]);
            e.preventDefault();
          }
        }
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsFocus(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      setFileList((prev) => [...prev, ...files]);
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#FAFAFA] dark:bg-[#111] overflow-y-auto relative">
      {/* Top Header - Simplified */}
      <div className="flex justify-end items-center px-8 py-6 w-full absolute top-0 left-0 z-10">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-white dark:bg-[#232734] flex items-center justify-center shadow-sm cursor-pointer hover:shadow-md transition-shadow">
            <Badge dot offset={[-2, 2]}>
              <span className="text-lg">🔔</span>
            </Badge>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col items-center justify-center w-full max-w-5xl mx-auto px-4 mt-10">
        {/* Title */}
        <h1 className="text-5xl font-medium text-gray-900 dark:text-gray-100 mb-12 tracking-tight">
          我能为你做什么？
        </h1>

        {/* Input Box Area */}
        <div
          className={cls(
            'w-full max-w-4xl bg-white dark:bg-[#232734] rounded-[24px] shadow-sm hover:shadow-md transition-all duration-300 border',
            isFocus
              ? 'border-blue-500/50 shadow-lg ring-4 ring-blue-500/5'
              : 'border-gray-200 dark:border-gray-800',
          )}
          onDragOver={(e) => {
            e.preventDefault();
            setIsFocus(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setIsFocus(false);
          }}
          onDrop={handleDrop}
        >
          <div className="p-4">
            {/* Selected Files Preview Area (Top of Input) */}
            {fileList.length > 0 && (
              <div className="flex gap-3 px-1 pb-3 overflow-x-auto scrollbar-hide">
                {fileList.map((file, index) => (
                  <FilePreview
                    key={index + file.name}
                    file={file}
                    onRemove={() => {
                      const newFileList = [...fileList];
                      newFileList.splice(index, 1);
                      setFileList(newFileList);
                    }}
                  />
                ))}
              </div>
            )}

            <Input.TextArea
              placeholder="分配一个任务或提问任何问题"
              className="!text-lg !bg-transparent !border-0 !resize-none placeholder:!text-gray-400 !text-gray-800 dark:!text-gray-200 !shadow-none !p-2 mb-4"
              autoSize={{ minRows: 2, maxRows: 6 }}
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onFocus={() => setIsFocus(true)}
              onBlur={() => setIsFocus(false)}
              onPaste={handlePaste}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  onSubmit();
                }
              }}
            />

            <div className="flex items-center justify-between px-2 pb-1">
              <div className="flex items-center gap-2">
                <Popover
                  content={plusMenuContent}
                  trigger="click"
                  placement="topLeft"
                  overlayClassName="!p-0"
                >
                  <Button
                    shape="circle"
                    icon={<PlusOutlined />}
                    className="!border-gray-200 dark:!border-gray-700 !text-gray-500 hover:!text-gray-700 dark:hover:!text-gray-300"
                  />
                </Popover>

                {/* App Selector (Moved from Upload position) */}
                <Dropdown menu={appMenuProps} trigger={['click']} placement="bottomLeft">
                  <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800/50 px-3 py-1.5 rounded-full border border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                    <span className="text-base">
                      {selectedApp?.icon ? (
                        <img src={selectedApp.icon} className="w-4 h-4" />
                      ) : (
                        '🤖'
                      )}
                    </span>
                    <span className="text-sm text-gray-700 dark:text-gray-300 font-medium max-w-[100px] truncate">
                      {selectedApp?.app_name || t('select_app', 'Select App')}
                    </span>
                    <DownOutlined className="text-xs text-gray-400" />
                  </div>
                </Dropdown>
              </div>

              <div className="flex items-center gap-3">
                {/* File Upload Icon Button (New Position) */}
                <Upload {...uploadProps} showUploadList={false}>
                  <Button
                    shape="circle"
                    icon={<PaperClipOutlined />}
                    className="!border-gray-200 dark:!border-gray-700 !text-gray-500 hover:!text-gray-700 dark:hover:!text-gray-300"
                  />
                </Upload>

                <Button
                  shape="circle"
                  type={userInput.trim() || fileList.length > 0 ? 'primary' : 'default'}
                  icon={<ArrowUpOutlined />}
                  className={cls(
                    'transition-all !w-9 !h-9 flex items-center justify-center',
                    userInput.trim() || fileList.length > 0
                      ? 'bg-black hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200'
                      : 'bg-gray-100 text-gray-400 border-none dark:bg-gray-800 dark:text-gray-600',
                  )}
                  onClick={onSubmit}
                  disabled={!userInput.trim() && fileList.length === 0}
                />
              </div>
            </div>

            {/* Selected Files List (Removed old list) */}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap justify-center gap-3 mt-8">
          <QuickActionButton icon={<FundProjectionScreenOutlined />} text="制作幻灯片" />
          <QuickActionButton icon={<DesktopOutlined />} text="创建网站" />
          <QuickActionButton icon={<CodeOutlined />} text="开发应用" />
          <QuickActionButton icon={<BulbOutlined />} text="设计" />
        </div>
      </div>

      <ConnectorsModal
        open={isConnectorsModalOpen}
        onCancel={() => setIsConnectorsModalOpen(false)}
        defaultTab={connectorsModalTab}
      />
    </div>
  );
}
