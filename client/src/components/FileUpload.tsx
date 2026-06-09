import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  FileExcelOutlined,
  FileImageOutlined,
  FileOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  FileWordOutlined,
  FileZipOutlined,
  InboxOutlined,
} from '@ant-design/icons';
import { Button, message, Progress, Tooltip, Upload } from 'antd';
import type { UploadProps } from 'antd/es/upload/interface';
import React, { useCallback, useMemo, useState } from 'react';

const { Dragger } = Upload;

export interface FileUploadProps {
  onUpload: (files: File[]) => void;
  accept?: string;
  maxSize?: number;
  multiple?: boolean;
  disabled?: boolean;
  maxCount?: number;
  className?: string;
  style?: React.CSSProperties;
}

interface FileItem {
  id: string;
  file: File;
  name: string;
  size: number;
  type: string;
  progress: number;
  status: 'pending' | 'uploading' | 'done' | 'error';
  error?: string;
}

const getFileIcon = (fileName: string): React.ReactNode => {
  const ext = fileName.split('.').pop()?.toLowerCase() || '';

  const iconMap: Record<string, React.ReactNode> = {
    pdf: <FilePdfOutlined style={{ color: 'var(--error)' }} />,
    doc: <FileWordOutlined style={{ color: 'var(--accent-primary)' }} />,
    docx: <FileWordOutlined style={{ color: 'var(--accent-primary)' }} />,
    xls: <FileExcelOutlined style={{ color: 'var(--success)' }} />,
    xlsx: <FileExcelOutlined style={{ color: 'var(--success)' }} />,
    txt: <FileTextOutlined style={{ color: 'var(--text-tertiary)' }} />,
    md: <FileTextOutlined style={{ color: 'var(--text-tertiary)' }} />,
    png: <FileImageOutlined style={{ color: 'var(--accent-tertiary)' }} />,
    jpg: <FileImageOutlined style={{ color: 'var(--accent-tertiary)' }} />,
    jpeg: <FileImageOutlined style={{ color: 'var(--accent-tertiary)' }} />,
    gif: <FileImageOutlined style={{ color: 'var(--accent-tertiary)' }} />,
    zip: <FileZipOutlined style={{ color: 'var(--warning)' }} />,
    rar: <FileZipOutlined style={{ color: 'var(--warning)' }} />,
    '7z': <FileZipOutlined style={{ color: 'var(--warning)' }} />,
  };

  return iconMap[ext] || <FileOutlined style={{ color: 'var(--text-tertiary)' }} />;
};

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const FileUpload: React.FC<FileUploadProps> = ({
  onUpload,
  accept,
  maxSize = 100,
  multiple = true,
  disabled = false,
  maxCount,
  className,
  style,
}) => {
  const [fileList, setFileList] = useState<FileItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  const acceptArray = useMemo(() => {
    if (!accept) return [];
    return accept.split(',').map((ext) => ext.trim().toLowerCase());
  }, [accept]);

  const validateFile = useCallback(
    (file: File): string | null => {
      if (maxSize && file.size > maxSize * 1024 * 1024) {
        return `文件大小超过限制 (${maxSize}MB)`;
      }

      if (acceptArray.length > 0) {
        const ext = '.' + file.name.split('.').pop()?.toLowerCase();
        const mimeType = file.type.toLowerCase();

        const isAccepted = acceptArray.some((acceptType) => {
          if (acceptType.startsWith('.')) {
            return ext === acceptType.toLowerCase();
          }
          if (acceptType.includes('/')) {
            if (acceptType.endsWith('/*')) {
              return mimeType.startsWith(acceptType.replace('/*', ''));
            }
            return mimeType === acceptType.toLowerCase();
          }
          return false;
        });

        if (!isAccepted) {
          return `不支持的文件类型: ${ext}`;
        }
      }

      return null;
    },
    [acceptArray, maxSize],
  );

  const addFiles = useCallback(
    (files: File[]) => {
      const newFiles: FileItem[] = [];

      for (const file of files) {
        const error = validateFile(file);

        if (error) {
          message.error(`${file.name}: ${error}`);
          continue;
        }

        if (maxCount && fileList.length + newFiles.length >= maxCount) {
          message.warning(`最多上传 ${maxCount} 个文件`);
          break;
        }

        const fileItem: FileItem = {
          id: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          file,
          name: file.name,
          size: file.size,
          type: file.type,
          progress: 0,
          status: 'pending',
        };

        newFiles.push(fileItem);
      }

      if (newFiles.length > 0) {
        setFileList((prev) => [...prev, ...newFiles]);
        simulateUpload(newFiles);
      }
    },
    [fileList.length, maxCount, validateFile],
  );

  const simulateUpload = useCallback((files: FileItem[]) => {
    files.forEach((fileItem) => {
      setFileList((prev) =>
        prev.map((f) => (f.id === fileItem.id ? { ...f, status: 'uploading' as const } : f)),
      );

      const totalSteps = 10;
      let currentStep = 0;

      const interval = setInterval(() => {
        currentStep++;
        const progress = Math.min((currentStep / totalSteps) * 100, 100);

        setFileList((prev) => prev.map((f) => (f.id === fileItem.id ? { ...f, progress } : f)));

        if (currentStep >= totalSteps) {
          clearInterval(interval);
          setFileList((prev) =>
            prev.map((f) =>
              f.id === fileItem.id ? { ...f, status: 'done' as const, progress: 100 } : f,
            ),
          );
        }
      }, 100);
    });
  }, []);

  const removeFile = useCallback((id: string) => {
    setFileList((prev) => prev.filter((f) => f.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setFileList([]);
  }, []);

  const handleUpload = useCallback(() => {
    const validFiles = fileList.filter((f) => f.status === 'done').map((f) => f.file);

    if (validFiles.length === 0) {
      message.warning('请先选择文件');
      return;
    }

    onUpload(validFiles);
  }, [fileList, onUpload]);

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!disabled) {
        setIsDragging(true);
      }
    },
    [disabled],
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      if (disabled) return;

      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) {
        if (!multiple && files.length > 1) {
          message.warning('只能上传一个文件');
          addFiles([files[0]!]);
        } else {
          addFiles(files);
        }
      }
    },
    [disabled, multiple, addFiles],
  );

  const uploadProps: UploadProps = {
    multiple,
    accept,
    disabled,
    showUploadList: false,
    beforeUpload: (file) => {
      addFiles([file]);
      return false;
    },
  };

  const doneCount = fileList.filter((f) => f.status === 'done').length;
  const uploadingCount = fileList.filter((f) => f.status === 'uploading').length;

  return (
    <div
      className={className}
      style={style}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <Dragger
        {...uploadProps}
        style={{
          background: isDragging ? 'var(--primary-50)' : 'var(--bg-color)',
          border: isDragging ? '2px dashed var(--primary-500)' : '2px dashed var(--border-color)',
          borderRadius: '12px',
          padding: '24px',
          transition: 'all 0.3s ease',
        }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined
            style={{
              fontSize: '48px',
              color: isDragging ? 'var(--primary-500)' : 'var(--text-tertiary)',
              transition: 'color 0.3s ease',
            }}
          />
        </p>
        <p
          className="ant-upload-text"
          style={{
            fontSize: '16px',
            fontWeight: 500,
            color: 'var(--text-primary)',
            marginBottom: '8px',
          }}
        >
          点击或拖拽文件到此区域上传
        </p>
        <p
          className="ant-upload-hint"
          style={{
            fontSize: '14px',
            color: 'var(--text-tertiary)',
          }}
        >
          {accept && (
            <span style={{ display: 'block', marginBottom: '4px' }}>支持的文件类型: {accept}</span>
          )}
          {maxSize && (
            <span style={{ display: 'block', marginBottom: '4px' }}>单个文件最大: {maxSize}MB</span>
          )}
          {maxCount && <span style={{ display: 'block' }}>最多上传: {maxCount} 个文件</span>}
          {!accept && !maxSize && !maxCount && multiple && <span>支持单个或批量上传</span>}
        </p>
      </Dragger>

      {fileList.length > 0 && (
        <div
          style={{
            marginTop: '16px',
            background: 'var(--bg-secondary)',
            borderRadius: '12px',
            border: '1px solid var(--border-color)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--border-color)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: 'var(--bg-elevated)',
            }}
          >
            <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
              已选择 {fileList.length} 个文件
              {uploadingCount > 0 && (
                <span style={{ color: 'var(--primary-500)', marginLeft: '8px' }}>
                  (上传中 {uploadingCount} 个)
                </span>
              )}
            </span>
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              onClick={clearAll}
              style={{ color: 'var(--text-tertiary)' }}
            >
              清空
            </Button>
          </div>

          <div style={{ maxHeight: '240px', overflowY: 'auto' }}>
            {fileList.map((fileItem) => (
              <div
                key={fileItem.id}
                style={{
                  padding: '12px 16px',
                  borderBottom: '1px solid var(--border-color)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  transition: 'background 0.2s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--bg-elevated)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                }}
              >
                <div style={{ fontSize: '24px', flexShrink: 0 }}>{getFileIcon(fileItem.name)}</div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      marginBottom: '4px',
                    }}
                  >
                    <Tooltip title={fileItem.name}>
                      <span
                        style={{
                          fontWeight: 500,
                          color: 'var(--text-primary)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                        }}
                      >
                        {fileItem.name}
                      </span>
                    </Tooltip>
                    <span
                      style={{
                        fontSize: '12px',
                        color: 'var(--text-tertiary)',
                        flexShrink: 0,
                      }}
                    >
                      {formatFileSize(fileItem.size)}
                    </span>
                  </div>

                  {fileItem.status === 'uploading' && (
                    <Progress
                      percent={Math.round(fileItem.progress)}
                      size="small"
                      showInfo={false}
                      strokeColor="var(--primary-500)"
                      style={{ margin: 0 }}
                    />
                  )}

                  {fileItem.status === 'error' && (
                    <span style={{ fontSize: '12px', color: 'var(--error)' }}>
                      {fileItem.error || '上传失败'}
                    </span>
                  )}
                </div>

                <div style={{ flexShrink: 0 }}>
                  {fileItem.status === 'done' && (
                    <CheckCircleOutlined style={{ color: 'var(--success)', fontSize: '18px' }} />
                  )}
                  {fileItem.status === 'uploading' && (
                    <span style={{ fontSize: '12px', color: 'var(--primary-500)' }}>
                      {Math.round(fileItem.progress)}%
                    </span>
                  )}
                  {fileItem.status === 'error' && (
                    <CloseCircleOutlined style={{ color: 'var(--error)', fontSize: '18px' }} />
                  )}
                  {(fileItem.status === 'done' || fileItem.status === 'error') && (
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={() => removeFile(fileItem.id)}
                      style={{
                        color: 'var(--text-tertiary)',
                        marginLeft: '8px',
                      }}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {fileList.length > 0 && (
        <div
          style={{
            marginTop: '16px',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '12px',
          }}
        >
          <Button onClick={clearAll}>取消</Button>
          <Button
            type="primary"
            onClick={handleUpload}
            disabled={uploadingCount > 0 || doneCount === 0}
            style={{
              borderRadius: '8px',
              minWidth: '100px',
            }}
          >
            确认上传 ({doneCount})
          </Button>
        </div>
      )}

      <style>{`
        .ant-upload-drag:hover {
          border-color: var(--primary-500) !important;
        }
        
        .ant-upload-drag .ant-upload-drag-icon {
          margin-bottom: 16px;
        }
        
        .ant-progress-bg {
          background-color: var(--primary-500) !important;
        }
      `}</style>
    </div>
  );
};

export default FileUpload;
