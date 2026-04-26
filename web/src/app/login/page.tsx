'use client';

import { authService } from '@/services/auth';
import { GithubOutlined, LoginOutlined, ThunderboltOutlined, UserOutlined, LockOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Divider, Form, Input, Spin } from 'antd';
import { useSearchParams, useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

const ERROR_MESSAGES: Record<string, string> = {
  user_disabled: '您的账号已被禁用，请联系管理员。',
  missing_params: 'OAuth 回调参数缺失，请重试。',
  invalid_state: 'OAuth 状态验证失败，请重试。',
  token_exchange_failed: 'OAuth token 获取失败，请重试。',
  userinfo_failed: '获取用户信息失败，请重试。',
  user_create_failed: '创建用户失败，请联系管理员。',
};

export default function LoginPage() {
  const [loading, setLoading] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [providers, setProviders] = useState<Array<{ id: string; type: string }>>([]);
  const [oauthEnabled, setOauthEnabled] = useState(false);
  const [localLoginEnabled, setLocalLoginEnabled] = useState(false);
  const [loginError, setLoginError] = useState('');
  const loadedRef = useRef(false);
  const searchParams = useSearchParams();
  const router = useRouter();
  const [form] = Form.useForm();
  const errorCode = searchParams?.get('error') || '';
  const errorMsg = errorCode ? ERROR_MESSAGES[errorCode] || `登录出错：${errorCode}` : '';

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    loadOAuthStatus();
  }, []);

  const loadOAuthStatus = async () => {
    setLoading(true);
    try {
      const status = await authService.getOAuthStatus();
      setOauthEnabled(status.enabled);
      setProviders(status.providers || []);
      setLocalLoginEnabled(status.local_login_enabled ?? false);
    } catch (error: any) {
      console.error('获取登录配置失败:', error);
      setOauthEnabled(false);
      setProviders([]);
      setLocalLoginEnabled(false);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = (providerId: string) => {
    const url = authService.getOAuthLoginUrl(providerId);
    window.location.href = url;
  };

  const handleLocalLogin = async (values: { username: string; password: string }) => {
    setLoginLoading(true);
    setLoginError('');
    try {
      const data = await authService.localLogin(values.username, values.password);
      // Store token and user info
      if (data.token) {
        localStorage.setItem('__db_gpt_tk_key', data.token);
      }
      const userInfo = {
        user_channel: 'local',
        user_no: data.user_no || String(data.user?.id || ''),
        nick_name: data.nick_name || data.user?.name || '',
        avatar_url: data.avatar_url || '',
        email: data.email || '',
        role: data.role || 'normal',
      };
      localStorage.setItem('__db_gpt_uinfo_key', JSON.stringify(userInfo));
      router.replace('/');
    } catch (error: any) {
      const msg = error?.response?.data?.detail || '登录失败，请检查用户名和密码';
      setLoginError(msg);
    } finally {
      setLoginLoading(false);
    }
  };

  if (loading) {
    return (
      <div className='flex items-center justify-center min-h-screen bg-gray-50'>
        <Spin size='large' />
      </div>
    );
  }

  if (!oauthEnabled && !localLoginEnabled) {
    return (
      <div className='flex items-center justify-center min-h-screen bg-gray-50'>
        <Card title='登录' style={{ width: 400 }}>
          <p className='text-gray-500'>OAuth2 登录未配置或未启用。请在 设置 → 系统配置 中配置 OAuth2 提供商。</p>
        </Card>
      </div>
    );
  }

  return (
    <div className='flex items-center justify-center min-h-screen bg-gray-50'>
      <Card title='登录' style={{ width: 400 }}>
        {(errorMsg || loginError) && (
          <Alert
            type='error'
            message={errorMsg || loginError}
            showIcon
            className='mb-4'
          />
        )}

        {localLoginEnabled && (
          <>
            <Form form={form} onFinish={handleLocalLogin} layout='vertical'>
              <Form.Item name='username' rules={[{ required: true, message: '请输入用户名' }]}>
                <Input prefix={<UserOutlined />} placeholder='用户名' size='large' />
              </Form.Item>
              <Form.Item name='password' rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password prefix={<LockOutlined />} placeholder='密码' size='large' />
              </Form.Item>
              <Form.Item>
                <Button type='primary' htmlType='submit' block size='large' loading={loginLoading}>
                  登录
                </Button>
              </Form.Item>
            </Form>

            {oauthEnabled && providers.length > 0 && (
              <Divider>或</Divider>
            )}
          </>
        )}

        {oauthEnabled && providers.length > 0 && (
          <div className='space-y-3'>
            {providers.map(p => {
              const getIcon = () => {
                if (p.type === 'github') return <GithubOutlined />;
                if (p.type === 'alibaba-inc') return <ThunderboltOutlined className='text-orange-500' />;
                return <LoginOutlined />;
              };
              const getLabel = () => {
                if (p.type === 'github') return '使用 GitHub 登录';
                if (p.type === 'alibaba-inc') return '使用 alibaba-inc 登录';
                return `使用 ${p.id} 登录`;
              };
              return (
                <Button key={p.id} block size='large' icon={getIcon()} onClick={() => handleLogin(p.id)}>
                  {getLabel()}
                </Button>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}