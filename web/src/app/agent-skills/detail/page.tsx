'use client';
import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Typography,
  Spin,
  Button,
  Form,
  Input,
  Select,
  Switch,
  message,
  Modal,
  Space,
  Tree,
  Tabs,
  Divider,
  Row,
  Col,
  Tag,
  Tooltip,
} from 'antd';
import {
  CodeOutlined,
  FileOutlined,
  FolderOutlined,
  SaveOutlined,
  ReloadOutlined,
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  FileTextOutlined,
  EditOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import dynamic from 'next/dynamic';
import { apiInterceptors } from '@/client/api';
import {
  getSkillDetail,
  listSkillFiles,
  readSkillFile,
  writeSkillFile,
  createSkillFile,
  deleteSkillFile,
  renameSkillFile,
  batchUploadSkillFiles,
  updateSkill,
} from '@/client/api/skill';

// Use dynamic import for the markdown editor to avoid SSR issues
const MdEditor = dynamic(() => import('react-markdown-editor-lite'), {
  ssr: false,
});
import 'react-markdown-editor-lite/lib/index.css';
import ReactMarkdown from 'react-markdown';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Option } = Select;

// File tree data structure
interface FileNode {
  name: string;
  path: string;
  isDirectory?: boolean;
  extension?: string;
  children?: FileNode[];
  key: string;
}

// editor wrapper for non-markdown files
const CodeEditor = ({ value, onChange, language }: { value: string; onChange: (value: string) => void; language: string }) => {
  return (
    <TextArea
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        fontFamily: 'monospace',
        height: '100%',
        minHeight: '500px',
        fontSize: '14px',
        lineHeight: '1.6',
      }}
      spellCheck={false}
    />
  );
};

type SkillFile = {
  name: string;
  path: string;
  size: number;
  is_directory: boolean;
  extension: string;
};

export default function SkillDetailPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const skillCode = searchParams.get('code') || '';

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingMetadata, setSavingMetadata] = useState(false);
  const [files, setFiles] = useState<SkillFile[]>([]);
  const [skillData, setSkillData] = useState<any>(null);

  // Editor state
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [originalContent, setOriginalContent] = useState('');

  // Metadata editing state
  const [metadataForm] = Form.useForm();
  const [metadataChanged, setMetadataChanged] = useState(false);
  const [originalMetadata, setOriginalMetadata] = useState<any>(null);

  // UI state
  const [isCreateFileModalVisible, setIsCreateFileModalVisible] = useState(false);
  const [isRenameModalVisible, setIsRenameModalVisible] = useState(false);
  const [renamingFile, setRenamingFile] = useState<string | null>(null);
  const [isUploadingFolder, setIsUploadingFolder] = useState(false);

  const [createFileForm] = Form.useForm();
  const [renameFileForm] = Form.useForm();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load skill data and files
  const loadSkillData = useCallback(async () => {
    if (!skillCode) return;

    setLoading(true);
    try {
      const [err, res] = await apiInterceptors(getSkillDetail({ skill_code: skillCode }));
      if (res) {
        setSkillData(res);
        setOriginalMetadata(res);
        // Populate metadata form
        metadataForm.setFieldsValue({
          name: res.name,
          type: res.type,
          description: res.description,
          author: res.author || '',
          version: res.version || '',
          available: res.available ?? true,
        });
      }
    } catch (error) {
      message.error('Failed to load skill details');
    } finally {
      setLoading(false);
    }
  }, [skillCode, metadataForm]);

  const loadFiles = useCallback(async () => {
    if (!skillCode) return;

    setLoading(true);
    try {
      const [err, res] = await apiInterceptors(listSkillFiles(skillCode));
      if (res) {
        setFiles(res.files || []);
        // Clear current file if it was deleted
        if (selectedFile && !res.files.find((f: SkillFile) => f.path === selectedFile)) {
          setSelectedFile(null);
          setFileContent('');
          setOriginalContent('');
        }
      }
    } catch (error) {
      console.error('Failed to load files:', error);
      message.error('Failed to load skill files. Please sync from Git first.');
    } finally {
      setLoading(false);
    }
  }, [skillCode, selectedFile]);

  const loadFileContent = useCallback(async (filePath: string) => {
    if (!filePath) return;

    setLoading(true);
    try {
      const [err, res] = await apiInterceptors(readSkillFile(skillCode, filePath));
      if (res) {
        setSelectedFile(filePath);
        setFileContent(res.content);
        setOriginalContent(res.content);
      }
    } catch (error) {
      message.error(`Failed to load file: ${filePath}`);
    } finally {
      setLoading(false);
    }
  }, [skillCode]);

  const saveFile = useCallback(async () => {
    if (!selectedFile) return;

    setSaving(true);
    try {
      const [err, res] = await apiInterceptors(writeSkillFile(skillCode, selectedFile, fileContent));
      if (res) {
        message.success('File saved successfully');
        setOriginalContent(fileContent);
      }
    } catch (error) {
      message.error('Failed to save file');
    } finally {
      setSaving(false);
    }
  }, [skillCode, selectedFile, fileContent]);

  const saveMetadata = useCallback(async () => {
    try {
      const values = await metadataForm.validateFields();
      setSavingMetadata(true);

      const [err, res] = await apiInterceptors(
        updateSkill({ ...values, skill_code: skillCode })
      );
      if (res) {
        message.success('Metadata updated successfully');
        setSkillData(res);
        setOriginalMetadata(res);
        setMetadataChanged(false);
      }
    } catch (error) {
      message.error('Failed to update metadata');
    } finally {
      setSavingMetadata(false);
    }
  }, [skillCode, metadataForm]);

  const handleCreateFile = useCallback(async () => {
    try {
      const values = createFileForm.getFieldsValue() as { fileName: string; filePath: string } || {};
      const fileNameVal = values.fileName;
      const filePathVal = values.filePath;

      if (!fileNameVal) {
        message.error('Please enter a file name');
        return;
      }

      const newFilePath = filePathVal ? `${filePathVal}/${fileNameVal}` : fileNameVal;
      const [err, res] = await apiInterceptors(createSkillFile(skillCode, newFilePath, ''));
      if (res) {
        message.success('File created successfully');
        setIsCreateFileModalVisible(false);
        createFileForm.resetFields();
        loadFiles();
        // Auto-select the new file
        loadFileContent(newFilePath);
      }
    } catch (error) {
      message.error('Failed to create file');
    }
  }, [skillCode, createFileForm, loadFiles, loadFileContent]);

  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [isDeleteModalVisible, setIsDeleteModalVisible] = useState(false);

  const openDeleteModal = useCallback((filePath: string) => {
    setDeletingFile(filePath);
    setIsDeleteModalVisible(true);
  }, []);

  const handleDeleteFileConfirm = useCallback(async () => {
    if (!deletingFile) return;

    try {
      const [err, res] = await apiInterceptors(deleteSkillFile(skillCode, deletingFile));
      if (res) {
        message.success('File deleted successfully');
        loadFiles();
        if (selectedFile === deletingFile) {
          setSelectedFile(null);
          setFileContent('');
          setOriginalContent('');
        }
      }
    } catch (error) {
      message.error('Failed to delete file');
    } finally {
      setIsDeleteModalVisible(false);
      setDeletingFile(null);
    }
  }, [skillCode, deletingFile, selectedFile, loadFiles]);

  const handleRenameFile = useCallback(async () => {
    if (!renamingFile) return;

    try {
      const values = await renameFileForm.validateFields();
      const newName = values.newName;

      if (!newName || newName === renamingFile.split('/').pop()) {
        message.info('File name unchanged');
        setIsRenameModalVisible(false);
        return;
      }

      // Construct new path by replacing the last part of the old path
      const pathParts = renamingFile.split('/');
      pathParts[pathParts.length - 1] = newName;
      const newPath = pathParts.join('/');

      const [err, res] = await apiInterceptors(renameSkillFile(skillCode, renamingFile, newPath));
      if (res) {
        message.success('File renamed successfully');
        setIsRenameModalVisible(false);
        renameFileForm.resetFields();
        loadFiles();
        // Update selected file if it was renamed
        if (selectedFile === renamingFile) {
          setSelectedFile(newPath);
        }
        setRenamingFile(null);
      }
    } catch (error) {
      message.error('Failed to rename file');
    }
  }, [skillCode, renamingFile, selectedFile, renameFileForm, loadFiles]);

  const openRenameModal = useCallback((filePath: string) => {
    setRenamingFile(filePath);
    const fileName = filePath.split('/').pop() || '';
    renameFileForm.setFieldsValue({ newName: fileName });
    setIsRenameModalVisible(true);
  }, [renameFileForm]);

  // Handle folder upload
  const handleFolderUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsUploadingFolder(true);
    try {
      const fileList: { file_path: string; content: string; is_base64?: boolean }[] = [];

      // Get the first file to determine the root folder name
      const firstFile = files[0];
      const webkitRelativePath = firstFile.webkitRelativePath;
      const rootFolderName = webkitRelativePath.split('/')[0];

      // Read all files
      const readPromises = Array.from(files).map(async (file) => {
        // Calculate relative path (remove root folder name)
        const relativePath = file.webkitRelativePath.replace(rootFolderName + '/', '');

        // For binary files, we use base64 encoding
        const isBinary = !file.type.startsWith('text/') && file.type !== 'application/json' && file.type !== '';

        if (isBinary) {
          const content = await new Promise<string>((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => {
              const base64 = reader.result as string;
              resolve(base64.split(',')[1]); // Remove data URL prefix
            };
            reader.readAsDataURL(file);
          });
          return { file_path: relativePath, content, is_base64: true };
        } else {
          const content = await new Promise<string>((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result as string);
            reader.readAsText(file);
          });
          return { file_path: relativePath, content, is_base64: false };
        }
      });

      const results = await Promise.all(readPromises);
      fileList.push(...results);

      if (fileList.length === 0) {
        message.error('No files found in selected folder');
        return;
      }

      const [err, res] = await apiInterceptors(batchUploadSkillFiles(skillCode, fileList, true));
      if (res) {
        message.success(`Uploaded ${res.success_count} files, failed ${res.failed_count}`);
        loadFiles();
      } else {
        message.error('Failed to upload folder');
      }
    } catch (error) {
      console.error('Folder upload error:', error);
      message.error('Failed to upload folder');
    } finally {
      setIsUploadingFolder(false);
      // Reset input so the same folder can be selected again
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }, [skillCode, loadFiles]);

  // Build file tree structure
  const buildFileTree = useCallback((files: SkillFile[]): FileNode[] => {
    const tree: Record<string, FileNode> = {};

    files.forEach(file => {
      const parts = file.path.split('/');
      let currentPath = '';

      parts.forEach((part, index) => {
        const isLast = index === parts.length - 1;
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        const key = currentPath;

        if (!tree[key]) {
          tree[key] = {
            name: part,
            path: currentPath,
            isDirectory: !isLast,
            key: currentPath,
            children: [],
          };
        }

        // Add to parent
        if (index > 0) {
          const parentPath = parts.slice(0, index).join('/');
          if (tree[parentPath]) {
            if (!tree[parentPath].children) {
              tree[parentPath].children = [];
            }
            if (!tree[parentPath].children?.find(c => c.key === key)) {
              tree[parentPath].children?.push(tree[key]);
            }
          }
        }
      });

      // Add extension to leaf nodes
      if (tree[file.path]) {
        tree[file.path].extension = file.extension;
      }
    });

    // Return root level items (no parent or parent doesn't exist)
    return Object.values(tree).filter(node => {
      const parentPath = node.path.split('/').slice(0, -1).join('/');
      return !parentPath || !tree[parentPath];
    });
  }, []);

  const fileTree = buildFileTree(files);

  // Render file tree item
  const renderTreeNode = (node: FileNode) => ({
    title: (
      <span className="flex items-center justify-between pr-2 group w-full">
        <span className="flex items-center gap-2 flex-1 min-w-0">
          {node.isDirectory ? (
            <FolderOutlined className="text-yellow-500 flex-shrink-0" />
          ) : (
            <FileOutlined className="text-blue-400 flex-shrink-0" />
          )}
          <span className="truncate">{node.name}</span>
        </span>
        {!node.isDirectory && (
          <span
            className="flex items-center gap-1 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity ml-2"
            onClick={(e) => e.stopPropagation()}
          >
            <Button
              type="text"
              size="small"
              className="text-blue-400 hover:text-blue-600"
              icon={<EditOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                openRenameModal(node.path);
              }}
            />
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                openDeleteModal(node.path);
              }}
            />
          </span>
        )}
      </span>
    ),
    key: node.key,
    children: node.children?.map(renderTreeNode),
  });

  const renderEditor = () => {
    if (!selectedFile) {
      return (
        <div className="flex items-center justify-center h-full min-h-[500px] text-gray-400">
          <div className="text-center">
            <FileOutlined className="text-6xl mb-4" />
            <p>Select a file to view or edit</p>
          </div>
        </div>
      );
    }

    const fileExt = (selectedFile.split('.').pop() || '').toLowerCase();
    const isMarkdown = fileExt === 'md';

    if (isMarkdown) {
      return (
        <MdEditor
          style={{ height: '600px' }}
          renderHTML={(text) => <ReactMarkdown>{text}</ReactMarkdown>}
          onChange={({ text }) => setFileContent(text)}
          value={fileContent}
        />
      );
    }

    return (
      <CodeEditor
        value={fileContent}
        onChange={setFileContent}
        language={fileExt || 'text'}
      />
    );
  };

  useEffect(() => {
    loadSkillData();
  }, [loadSkillData]);

  // Load files on mount
  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  // Auto-select SKILL.md after files are loaded
  useEffect(() => {
    if (files.length > 0 && !selectedFile) {
      const skillMd = files.find((f: SkillFile) =>
        f.path === 'SKILL.md' || f.name === 'SKILL.md'
      );
      if (skillMd) {
        loadFileContent(skillMd.path);
      } else {
        const firstFile = files.find((f: SkillFile) => !f.is_directory);
        if (firstFile) {
          loadFileContent(firstFile.path);
        }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files]);

  if (loading && !skillData) {
    return (
      <div className="flex justify-center items-center h-screen">
        <Spin size="large" />
      </div>
    );
  }

  const hasUnsavedChanges = fileContent !== originalContent;

  return (
    <div className="h-screen flex flex-col bg-[#FAFAFA] dark:bg-[#111]">
      {/* Header */}
      <div className="bg-white dark:bg-[#1f1f1f] border-b border-gray-200 dark:border-gray-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={() => router.back()}
            >
              Back
            </Button>
            <div>
              <Title level={3} className="m-0 !mb-1">
                {skillData?.name || 'Skill Detail'}
              </Title>
              <div className="flex items-center gap-3">
                <Text type="secondary">Code: {skillCode}</Text>
                {skillData?.repo_url && (
                  <>
                    <Text type="secondary">•</Text>
                    <Tag color="green" size="small">Git</Tag>
                  </>
                )}
              </div>
            </div>
          </div>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => loadFiles()}
            >
              Refresh
            </Button>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              webkitdirectory="true"
              directory="true"
              multiple
              onChange={handleFolderUpload}
            />
            <Button
              icon={<UploadOutlined />}
              onClick={() => fileInputRef.current?.click()}
              loading={isUploadingFolder}
            >
              Upload Folder
            </Button>
            <Button
              icon={<PlusOutlined />}
              onClick={() => createFileForm.resetFields() || setIsCreateFileModalVisible(true)}
            >
              New File
            </Button>
          </Space>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden">
        <Tabs
          defaultActiveKey="editor"
          className="h-full"
          items={[
            {
              key: 'editor',
              label: (
                <span className="flex items-center gap-2">
                  <CodeOutlined />
                  File Editor
                </span>
              ),
              children: (
                <div className="flex h-[calc(100vh-140px)]">
                  {/* File Tree Sidebar */}
                  <div className="w-64 bg-white dark:bg-[#1f1f1f] border-r border-gray-200 dark:border-gray-800 overflow-y-auto p-4 flex-shrink-0">
                    <div className="mb-4">
                      <Text strong>Files ({files.length})</Text>
                    </div>
                    {fileTree.length > 0 ? (
                      <Tree
                        defaultExpandAll
                        showIcon
                        treeData={fileTree.map(renderTreeNode)}
                        onSelect={(keys) => {
                          const key = keys[0] as string;
                          if (key) {
                            loadFileContent(key);
                          }
                        }}
                        selectedKeys={selectedFile ? [selectedFile] : []}
                      />
                    ) : (
                      <div className="text-gray-400 text-center py-8">
                        <p>No files found</p>
                        <p className="text-sm">Sync from Git to get skill files</p>
                      </div>
                    )}
                  </div>

                  {/* Editor Area */}
                  <div className="flex-1 overflow-auto p-6">
                    <div className="max-w-5xl mx-auto">
                      <Card
                        title={
                          <div className="flex items-center justify-between">
                            <Space>
                              <FileTextOutlined />
                              <span>{selectedFile || 'No file selected'}</span>
                            </Space>
                            {hasUnsavedChanges && (
                              <Text type="warning" className="text-sm">
                                * Unsaved changes
                              </Text>
                            )}
                          </div>
                        }
                        extra={
                          <Button
                            type="primary"
                            icon={<SaveOutlined />}
                            onClick={saveFile}
                            loading={saving}
                            disabled={!selectedFile || !hasUnsavedChanges}
                          >
                            Save File
                          </Button>
                        }
                        className="shadow-sm"
                      >
                        {renderEditor()}
                      </Card>
                    </div>
                  </div>
                </div>
              ),
            },
            {
              key: 'metadata',
              label: (
                <span className="flex items-center gap-2">
                  <InfoCircleOutlined />
                  Metadata
                  {metadataChanged && (
                    <Tag color="orange" size="small">Modified</Tag>
                  )}
                </span>
              ),
              children: (
                <div className="flex-1 overflow-auto p-6">
                  <div className="max-w-4xl mx-auto">
                    <Card
                      title="Skill Metadata"
                      extra={
                        <Button
                          type="primary"
                          icon={<SaveOutlined />}
                          onClick={saveMetadata}
                          loading={savingMetadata}
                          disabled={!metadataChanged}
                        >
                          Save Changes
                        </Button>
                      }
                      className="shadow-sm"
                    >
                      <Form
                        form={metadataForm}
                        layout="vertical"
                        onValuesChange={() => setMetadataChanged(true)}
                      >
                        <Row gutter={16}>
                          <Col span={12}>
                            <Form.Item
                              name="name"
                              label="Skill Name"
                              rules={[{ required: true, message: 'Please enter skill name' }]}
                            >
                              <Input placeholder="Skill name" />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item
                              name="type"
                              label="Type"
                              rules={[{ required: true, message: 'Please select skill type' }]}
                            >
                              <Select placeholder="Select skill type">
                                <Option value="python">Python</Option>
                                <Option value="tool">Tool</Option>
                                <Option value="retrieval">Retrieval</Option>
                                <Option value="action">Action</Option>
                              </Select>
                            </Form.Item>
                          </Col>
                        </Row>

                        <Row gutter={16}>
                          <Col span={12}>
                            <Form.Item name="author" label="Author">
                              <Input placeholder="Author name (e.g., Anthropic, OpenAI)" />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item name="version" label="Version">
                              <Input placeholder="Version (e.g., 1.0.0)" />
                            </Form.Item>
                          </Col>
                        </Row>

                        <Row gutter={16}>
                          <Col span={8}>
                            <Form.Item name="available" label="Available" valuePropName="checked">
                              <Switch />
                            </Form.Item>
                          </Col>
                          <Col span={8}>
                            <div className="pt-2">
                              <Text type="secondary">Source</Text>
                              <div>
                                {skillData?.repo_url ? (
                                  <>
                                    <Tag color="green">Git</Tag>
                                    <Tooltip title={skillData.repo_url}>
                                      <Tag color="blue" className="cursor-pointer">
                                        {skillData.repo_url.replace('https://github.com/', '').replace('.git', '')}
                                      </Tag>
                                    </Tooltip>
                                  </>
                                ) : (
                                  <Tag>Local</Tag>
                                )}
                              </div>
                            </div>
                          </Col>
                          <Col span={8}>
                            {skillData?.commit_id && (
                              <div className="pt-2">
                                <Text type="secondary">Commit</Text>
                                <div>
                                  <Tooltip title={skillData.commit_id}>
                                    <Tag color="purple" className="cursor-pointer">
                                      {skillData.commit_id.substring(0, 8)}
                                    </Tag>
                                  </Tooltip>
                                </div>
                              </div>
                            )}
                          </Col>
                        </Row>

                        <Divider />

                        <Form.Item
                          name="description"
                          label="Description"
                          rules={[{ required: true, message: 'Please enter description' }]}
                        >
                          <TextArea
                            rows={4}
                            placeholder="Describe what this skill does and when Claude should use it"
                            showCount
                            maxLength={500}
                          />
                        </Form.Item>
                      </Form>

                      {skillData && skillData.content && (
                        <>
                          <Divider />
                          <div>
                            <Text type="secondary">SKILL.md Preview</Text>
                            <div className="mt-2 p-4 bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 max-h-60 overflow-auto">
                              <pre className="whitespace-pre-wrap text-sm">{skillData.content.substring(0, 1000)}...</pre>
                            </div>
                          </div>
                        </>
                      )}
                    </Card>
                  </div>
                </div>
              ),
            },
          ]}
        />
      </div>

      {/* Create File Modal */}
      <Modal
        title="Create New File"
        open={isCreateFileModalVisible}
        onOk={handleCreateFile}
        onCancel={() => createFileForm.resetFields() || setIsCreateFileModalVisible(false)}
      >
        <Form form={createFileForm} layout="vertical">
          <Form.Item
            name="fileName"
            label="File Name"
            rules={[{ required: true, message: 'Please enter file name' }]}
          >
            <Input placeholder="e.g. new_file.md, template.js" />
          </Form.Item>
          <Form.Item
            name="filePath"
            label="File Path (optional)"
            help="Leave empty to create in root, or specify directory like templates/ to create in subdirectory"
          >
            <Input placeholder="directory/path" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Delete File Confirmation Modal */}
      <Modal
        title="Delete File"
        open={isDeleteModalVisible}
        onOk={handleDeleteFileConfirm}
        onCancel={() => {
          setIsDeleteModalVisible(false);
          setDeletingFile(null);
        }}
        okText="Delete"
        okType="danger"
        cancelText="Cancel"
      >
        <p>Are you sure you want to delete <strong>{deletingFile}</strong>?</p>
        <p className="text-gray-500 text-sm mt-2">This action cannot be undone.</p>
      </Modal>

      {/* Rename File Modal */}
      <Modal
        title="Rename File"
        open={isRenameModalVisible}
        onOk={handleRenameFile}
        onCancel={() => {
          setIsRenameModalVisible(false);
          renameFileForm.resetFields();
          setRenamingFile(null);
        }}
      >
        <Form form={renameFileForm} layout="vertical">
          <Form.Item
            name="newName"
            label="New File Name"
            rules={[{ required: true, message: 'Please enter new file name' }]}
          >
            <Input placeholder="e.g. new_name.md" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Unsaved changes warning when leaving */}
      {(hasUnsavedChanges || metadataChanged) && (
        <div className="fixed bottom-0 left-0 right-0 bg-orange-100 dark:bg-orange-900/30 border-t border-orange-300 dark:border-orange-700 px-6 py-3">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <Text type="secondary">
              You have unsaved changes. Make sure to save before leaving.
            </Text>
            <Space>
              {hasUnsavedChanges && (
                <Button type="default" onClick={saveFile} loading={saving}>
                  Save File
                </Button>
              )}
              {metadataChanged && (
                <Button type="default" onClick={saveMetadata} loading={savingMetadata}>
                  Save Metadata
                </Button>
              )}
            </Space>
          </div>
        </div>
      )}
    </div>
  );
}