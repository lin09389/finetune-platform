import {
  CopyOutlined,
  DeleteOutlined,
  EyeOutlined,
  PictureOutlined,
  ScanOutlined,
} from '@ant-design/icons';
import type { UploadFile, UploadProps } from 'antd';
import { Button, Card, Image, message, Modal, Space, Spin, Typography, Upload } from 'antd';
import React, { useCallback, useRef, useState } from 'react';
import { API_BASE_URL } from '../services/api';

const { Text } = Typography;

interface ImageUploadProps {
  onUpload: (file: File, preview: string) => void;
  onOCR?: (result: OCRResult) => void;
  accept?: string;
  maxSize?: number;
  showOCR?: boolean;
}

interface OCRResult {
  text: string;
  confidence: number;
  regions?: Array<{
    bounding_box: string;
    text: string;
    confidence: number;
  }>;
}

const ImageUpload: React.FC<ImageUploadProps> = ({
  onUpload,
  onOCR,
  accept = 'image/*',
  maxSize = 10 * 1024 * 1024,
  showOCR = true,
}) => {
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewImage, setPreviewImage] = useState('');
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrResult, setOcrResult] = useState<OCRResult | null>(null);
  const fileRef = useRef<File | null>(null);

  const beforeUpload = useCallback(
    (file: File) => {
      if (!file.type.startsWith('image/')) {
        message.error('只能上传图片文件');
        return false;
      }

      if (file.size > maxSize) {
        message.error(`图片大小不能超过 ${Math.round(maxSize / 1024 / 1024)}MB`);
        return false;
      }

      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const preview = reader.result as string;
        setPreviewImage(preview);
        setFileList([
          {
            uid: file.name,
            name: file.name,
            status: 'done',
            url: preview,
          },
        ]);
        fileRef.current = file;
        onUpload(file, preview);
      };

      return false;
    },
    [maxSize, onUpload],
  );

  const handleOCR = useCallback(async () => {
    if (!previewImage) {
      message.warning('请先上传图片');
      return;
    }

    setOcrLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/ocr`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_base64: previewImage.split(',')[1],
        }),
      });

      if (!response.ok) {
        message.error('OCR 识别失败');
        return;
      }

      const result = await response.json();
      setOcrResult(result);
      onOCR?.(result);
      message.success('OCR 识别完成');
    } catch {
      message.error('OCR 识别失败');
    } finally {
      setOcrLoading(false);
    }
  }, [onOCR, previewImage]);

  const handleCopyText = useCallback(async () => {
    if (!ocrResult?.text) return;

    try {
      await navigator.clipboard.writeText(ocrResult.text);
      message.success('文本已复制');
    } catch {
      message.error('复制失败');
    }
  }, [ocrResult]);

  const handleRemove = useCallback(() => {
    setFileList([]);
    setPreviewImage('');
    setOcrResult(null);
    fileRef.current = null;
  }, []);

  const uploadProps: UploadProps = {
    fileList,
    beforeUpload,
    onRemove: () => {
      handleRemove();
      return true;
    },
    accept,
    maxCount: 1,
    showUploadList: false,
  };

  return (
    <div className="image-upload-container">
      {!previewImage ? (
        <Upload.Dragger {...uploadProps} style={{ padding: 24 }}>
          <p className="ant-upload-drag-icon">
            <PictureOutlined style={{ fontSize: 48, color: 'var(--accent-primary)' }} />
          </p>
          <p className="ant-upload-text">点击或拖拽图片到此区域</p>
          <p className="ant-upload-hint">
            支持 JPG、PNG、GIF 格式，最大 {Math.round(maxSize / 1024 / 1024)}MB
          </p>
        </Upload.Dragger>
      ) : (
        <Card
          size="small"
          style={{ marginBottom: 16 }}
          extra={
            <Space>
              {showOCR && (
                <Button
                  icon={<ScanOutlined />}
                  onClick={() => void handleOCR()}
                  loading={ocrLoading}
                >
                  OCR 识别
                </Button>
              )}
              <Button icon={<EyeOutlined />} onClick={() => setPreviewVisible(true)}>
                预览
              </Button>
              <Button danger icon={<DeleteOutlined />} onClick={handleRemove}>
                删除
              </Button>
            </Space>
          }
        >
          <div style={{ display: 'flex', gap: 16 }}>
            <Image
              src={previewImage}
              alt="preview"
              width={150}
              height={150}
              style={{ objectFit: 'cover', borderRadius: 8 }}
              preview={false}
            />
            <div style={{ flex: 1 }}>
              {ocrLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin tip="OCR 识别中..." />
                </div>
              ) : ocrResult ? (
                <div>
                  <div style={{ marginBottom: 8 }}>
                    <Text strong>识别结果</Text>
                    <Text type="secondary" style={{ marginLeft: 8 }}>
                      置信度 {(ocrResult.confidence * 100).toFixed(1)}%
                    </Text>
                    <Button
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() => void handleCopyText()}
                      style={{ marginLeft: 8 }}
                    >
                      复制
                    </Button>
                  </div>
                  <div
                    style={{
                      background: '#f5f5f5',
                      padding: 12,
                      borderRadius: 6,
                      maxHeight: 200,
                      overflow: 'auto',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {ocrResult.text}
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '100%',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <ScanOutlined style={{ fontSize: 32, marginBottom: 8 }} />
                  <Text type="secondary">点击 OCR 识别按钮提取图片中的文字</Text>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      <Modal
        open={previewVisible}
        footer={null}
        onCancel={() => setPreviewVisible(false)}
        width="80%"
        centered
      >
        <img src={previewImage} alt="preview" style={{ width: '100%', borderRadius: 8 }} />
      </Modal>
    </div>
  );
};

export default ImageUpload;
