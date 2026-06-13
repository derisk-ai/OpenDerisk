"use client";
import { ChatContext } from "@/contexts";
import {
  DatabaseOutlined,
  PlusOutlined,
  ReadOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useContext, useEffect, useState } from "react";
import { Button, Drawer, Input, Modal, Spin, Steps, Tag, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { debounce } from "lodash";
import {
  apiInterceptors,
  delSpace,
  getSpaceConfig,
  getSpaceList,
  newDialogue,
} from "@/client/api";
import { File, ISpace, IStorage, StepChangeParams } from "@/types/knowledge";
import BlurredCard, {
  InnerDropdown,
  ChatButton,
} from "@/components/blurred-card";
import MemoryStatusDrawer from "@/components/knowledge/memory-status-drawer";
import moment from "moment";
import { useRouter } from "next/navigation";
import SpaceForm from "@/components/knowledge/space-form";
import DocUploadForm from "@/components/knowledge/doc-upload-form";
import DocTypeForm from "@/components/knowledge/doc-type-form";
import Segmentation from "@/components/knowledge/segmentation";
import DocPanel from "@/components/knowledge/doc-panel";
import classNames from "classnames";

export default function Knowledge() {
  const [spaceList, setSpaceList] = useState<Array<ISpace> | null>([]);
  const [isAddShow, setIsAddShow] = useState<boolean>(false);
  const [isPanelShow, setIsPanelShow] = useState<boolean>(false);
  const [currentSpace, setCurrentSpace] = useState<ISpace>();
  const [activeStep, setActiveStep] = useState<number>(0);
  const [spaceName, setSpaceName] = useState<string>("");
  const [files, setFiles] = useState<Array<File>>([]);
  const [docType, setDocType] = useState<string>("");
  const [addStatus, setAddStatus] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [spaceConfig, setSpaceConfig] = useState<IStorage | null>(null);
  const [embeddingModels, setEmbeddingModels] = useState<Array<{ name: string; provider?: string }>>([]);

  // Memory drawer state
  const [isMemoryDrawerOpen, setIsMemoryDrawerOpen] = useState(false);

  const { t } = useTranslation();
  const addKnowledgeSteps = [
    { title: t("Knowledge_Space_Config") },
    { title: t("Choose_a_Datasource_type") },
    { title: t("Upload") },
    { title: t("Segmentation") },
  ];
  const router = useRouter();

  async function getSpaces(params?: any) {
    setLoading(true);
    const [_, data] = await apiInterceptors(getSpaceList({ ...params }));
    setLoading(false);
    setSpaceList(data);
  }

  async function getSpaceConfigs() {
    const [_, data] = await apiInterceptors(getSpaceConfig());
    if (!data) return null;
    setSpaceConfig(data.storage);
    if (data.embedding_models) {
      setEmbeddingModels(data.embedding_models);
    }
  }

  useEffect(() => {
    getSpaces();
    getSpaceConfigs();
  }, []);

  const handleChat = async (space: ISpace) => {
    const [_, data] = await apiInterceptors(
      newDialogue({
        app_code: "chat_knowledge"
      })
    );

    if (data?.conv_uid) {
      router.push(`/chat?conv_uid=${data.conv_uid}&app_code=chat_knowledge&knowledge=${space.knowledge_id}`);
    }
  };

  const handleStepChange = ({
    label,
    spaceName,
    docType,
    files,
  }: StepChangeParams) => {
    if (label === "finish") {
      setIsAddShow(false);
      getSpaces();
      setSpaceName("");
      setDocType("");
      setAddStatus("finish");
      localStorage.removeItem("cur_space_id");
    } else if (label === "forward") {
      activeStep === 0 && getSpaces();
      setActiveStep((step) => step + 1);
    } else {
      setActiveStep((step) => step - 1);
    }
    files && setFiles(files);
    spaceName && setSpaceName(spaceName);
    docType && setDocType(docType);
  };

  function onAddDoc(spaceName: string) {
    setSpaceName(spaceName);
    setActiveStep(1);
    setIsAddShow(true);
    setAddStatus("start");
  }

  const showDeleteConfirm = (space: ISpace) => {
    Modal.confirm({
      title: t("Tips"),
      icon: <WarningOutlined />,
      content: `${t("Del_Knowledge_Tips")}?`,
      okText: "Yes",
      okType: "danger",
      cancelText: "No",
      async onOk() {
        await apiInterceptors(delSpace({ name: space?.name }));
        getSpaces();
      },
    });
  };

  const onSearch = async (e: any) => {
    getSpaces({ name: e.target.value });
  };

  const openMemoryDrawer = (space: ISpace) => {
    setCurrentSpace(space);
    setIsMemoryDrawerOpen(true);
  };

  // Group spaces by type for better organization
  const memorySpaces = spaceList?.filter(s => s.vector_type === "Memory") || [];
  const otherSpaces = spaceList?.filter(s => s.vector_type !== "Memory") || [];

  // Aggregate stats for the header strip
  const totalMemoryEntries = memorySpaces.reduce(
    (sum, s) => sum + (Number(s.docs) || 0),
    0,
  );

  const isMemory = (space: ISpace) => space.vector_type === "Memory";

  const renderSpaceCard = (space: ISpace) => (
    <BlurredCard
      onClick={() => {
        setCurrentSpace(space);
        setIsPanelShow(true);
        localStorage.setItem("cur_space_id", JSON.stringify(space.id));
      }}
      description={space.desc}
      name={space.name}
      key={space.id}
      logo={
        space.domain_type === "FinancialReport"
          ? "/models/fin_report.jpg"
          : space.vector_type === "KnowledgeGraph"
          ? "/models/knowledge-graph.png"
          : space.vector_type === "FullText"
          ? "/models/knowledge-full-text.jpg"
          : space.vector_type === "Memory"
          ? "/models/knowledge-memory.jpg"
          : "/models/knowledge-default.jpg"
      }
      RightTop={
        <InnerDropdown
          menu={{
            items: [
              {
                key: "del",
                label: (
                  <span
                    className="text-red-400"
                    onClick={() => showDeleteConfirm(space)}
                  >
                    {t("Delete")}
                  </span>
                ),
              },
            ],
          }}
        />
      }
      rightTopHover={false}
      Tags={
        <div className="flex item-center flex-wrap gap-y-1">
          <Tooltip title={isMemory(space) ? t("Memory_Entries") : t("Document")}>
            <Tag>
              <span className="flex items-center gap-1">
                {isMemory(space) ? (
                  <DatabaseOutlined className="mt-[1px]" />
                ) : (
                  <ReadOutlined className="mt-[1px]" />
                )}
                {space.docs}
              </span>
            </Tag>
          </Tooltip>
          <Tag>
            <span className="flex items-center gap-1">
              {space.domain_type || "Normal"}
            </span>
          </Tag>
          {space.vector_type ? (
            <Tag>
              <span className="flex items-center gap-1">
                {space.vector_type}
              </span>
            </Tag>
          ) : null}
          {isMemory(space) && Number(space.docs) > 0 && (
            <Tag color="green" className="border-0">
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
                {t("Memory_Active")}
              </span>
            </Tag>
          )}
        </div>
      }
      LeftBottom={
        <div className="flex gap-2">
          <span>{space.owner}</span>
          <span>•</span>
          {space?.gmt_modified && (
            <span>
              {moment(space?.gmt_modified).fromNow() +
                " " +
                t("update")}
            </span>
          )}
        </div>
      }
      RightBottom={
        <div className="flex gap-2">
          {space.vector_type === "Memory" && (
            <Button
              size="small"
              type="default"
              className="border-purple-300 text-purple-600 hover:border-purple-500 hover:text-purple-700"
              onClick={(e) => {
                e.stopPropagation();
                openMemoryDrawer(space);
              }}
            >
              {t("Memory_Status")}
            </Button>
          )}
          <ChatButton
            text={t("start_chat")}
            onClick={() => {
              handleChat(space);
            }}
          />
        </div>
      }
    />
  );

  return (
    <Spin spinning={loading}>
      <div className="page-body p-4 md:p-6 min-h-screen">
        {/* Header */}
        <div className="flex justify-between items-start mb-6 flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">
              {t("Knowledge_Space")}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t("Knowledge_Space_Config")}
            </p>
            {/* Stats strip */}
            <div className="flex items-center gap-5 mt-4">
              <StatPill
                icon={<ReadOutlined />}
                label={t("Knowledge_Spaces")}
                value={spaceList?.length || 0}
                color="text-blue-500"
              />
              <StatPill
                icon={<DatabaseOutlined />}
                label={t("Memory_Store")}
                value={memorySpaces.length}
                color="text-purple-500"
              />
              <StatPill
                icon={<ThunderboltOutlined />}
                label={t("Memory_Total_Entries")}
                value={totalMemoryEntries}
                color="text-emerald-500"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Input
              variant="filled"
              prefix={<SearchOutlined />}
              placeholder={t("please_enter_the_keywords")}
              onChange={debounce(onSearch, 300)}
              allowClear
              className="w-[260px] h-[40px] border-1 border-white backdrop-filter backdrop-blur-lg bg-white bg-opacity-30 dark:border-[#6f7f95] dark:bg-[#6f7f95] dark:bg-opacity-60"
            />
            <Button
              className="border-none text-white bg-button-gradient"
              icon={<PlusOutlined />}
              onClick={() => {
                setIsAddShow(true);
              }}
            >
              {t("create_knowledge")}
            </Button>
          </div>
        </div>

        {/* Content */}
        {spaceList && spaceList.length > 0 ? (
          <div className="space-y-8 overflow-y-auto">
            {/* Memory spaces section */}
            {memorySpaces.length > 0 && (
              <section>
                <div className="mb-4">
                  <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-gradient-to-r from-purple-500 to-indigo-500" />
                    {t("Memory_Store")}
                    <Tag color="purple" className="ml-1">{memorySpaces.length}</Tag>
                  </h2>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 ml-4">
                    {t("Memory_Store_Subtitle")}
                  </p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                  {memorySpaces.map(renderSpaceCard)}
                </div>
              </section>
            )}

            {/* Other spaces section */}
            {otherSpaces.length > 0 && (
              <section>
                <div className="mb-4">
                  <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-gradient-to-r from-blue-500 to-cyan-500" />
                    {t("Knowledge_Spaces")}
                    <Tag color="blue" className="ml-1">{otherSpaces.length}</Tag>
                  </h2>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 ml-4">
                    {t("Knowledge_Spaces_Subtitle")}
                  </p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                  {otherSpaces.map(renderSpaceCard)}
                </div>
              </section>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400">
            <ReadOutlined className="text-6xl mb-4" />
            <p className="text-lg">{t("No_data")}</p>
            <p className="text-sm mt-1">
              {spaceConfig ? t("create_knowledge") : t("Loading")}...
            </p>
          </div>
        )}
      </div>

      {/* Document Panel */}
      <Modal
        className="h-5/6 overflow-hidden"
        open={isPanelShow}
        width={"70%"}
        onCancel={() => setIsPanelShow(false)}
        footer={null}
        destroyOnHidden={true}
      >
        <DocPanel
          space={currentSpace!}
          onAddDoc={onAddDoc}
          onDeleteDoc={getSpaces}
          addStatus={addStatus}
        />
      </Modal>

      {/* Memory Status Drawer */}
      <Drawer
        title={null}
        open={isMemoryDrawerOpen}
        onClose={() => setIsMemoryDrawerOpen(false)}
        width={720}
        placement="right"
        destroyOnHidden
      >
        {currentSpace && (
          <MemoryStatusDrawer
            knowledgeId={String(currentSpace.knowledge_id)}
            spaceName={currentSpace.name}
          />
        )}
      </Drawer>

      {/* Create Space Modal */}
      <Modal
        title={t("New_knowledge_base")}
        centered
        open={isAddShow}
        destroyOnHidden={true}
        onCancel={() => {
          setIsAddShow(false);
        }}
        width={1000}
        afterClose={() => {
          setActiveStep(0);
          getSpaces();
        }}
        footer={null}
      >
        <Steps current={activeStep} items={addKnowledgeSteps} />
        {activeStep === 0 && (
          <SpaceForm
            handleStepChange={handleStepChange}
            spaceConfig={spaceConfig}
            embeddingModels={embeddingModels}
          />
        )}
        {activeStep === 1 && (
          <DocTypeForm handleStepChange={handleStepChange} />
        )}
        <DocUploadForm
          className={classNames({ hidden: activeStep !== 2 })}
          spaceName={spaceName}
          docType={docType}
          handleStepChange={handleStepChange}
        />
        {activeStep === 3 && (
          <Segmentation
            spaceName={spaceName}
            docType={docType}
            uploadFiles={files}
            handleStepChange={handleStepChange}
          />
        )}
      </Modal>
    </Spin>
  );
}

function StatPill({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className={`text-base ${color}`}>{icon}</span>
      <span className="text-xl font-bold text-gray-800 dark:text-gray-100 leading-none">
        {value}
      </span>
      <span className="text-xs text-gray-400 dark:text-gray-500">{label}</span>
    </div>
  );
}
