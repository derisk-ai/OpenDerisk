import '@/pages/construct/mpc/index.css';
import { Button, Upload } from 'antd';
import { useTranslation } from 'react-i18next';

interface IProps {
  value?: string;
  onChange?: (value: any) => void;
}

const CustomUpload = ({ value, onChange }: IProps) => {
  const { t } = useTranslation();

  const handleChange = info => {
    if (info?.file && info?.fileList?.length) {
      const reader = new FileReader();
      reader.readAsDataURL(info.file);
      reader.onload = () => {
        onChange?.(reader?.result); // 将 base64 传给 Form
      };
    } else {
      onChange?.(null); // 移除图片时，清空 value
    }
  };

  return (
    <Upload
      beforeUpload={() => false} // 阻止自动上传
      onChange={handleChange}
      showUploadList={{ showPreviewIcon: true, showRemoveIcon: true }}
      maxCount={1}
      accept={'.png,.jpg,.jpeg,.gif'}
      onRemove={() => {
        onChange?.(null); // 移除图片时，清空 value
      }}
      className='customUploadBox'
    >
      <Button type='dashed' className='mb-2 w-full'>
        {' '}
        {t('upload_image')}
      </Button>
      {value && <img src={value} alt='preview' style={{ width: 100 }} />}
    </Upload>
  );
};

export default CustomUpload;
