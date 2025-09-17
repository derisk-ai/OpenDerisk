'use client';
import { useTranslation } from 'react-i18next';

export default function Construct() {
  const { t } = useTranslation();
  return (
    <div>{t('application_construct_page')}</div> 
  )
}
