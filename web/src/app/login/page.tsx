'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Alert, Card, Button, Spin } from 'antd';
import { GithubOutlined, LoginOutlined } from '@ant-design/icons';
import { authService } from '@/services/auth';
import { useSearchParams } from 'next/navigation';

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
  const [providers, setProviders] = useState<Array<{ id: string; type: string }>>([]);
  const [oauthEnabled, setOauthEnabled] = useState(false);
  const loadedRef = useRef(false);
  const searchParams = useSearchParams();
  const errorCode = searchParams?.get('error') || '';
  const errorMsg = errorCode ? (ERROR_MESSAGES[errorCode] || `登录出错：${errorCode}`) : '';

  useEffect(() => {
    // 防止重复加载
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
    } catch (error: any) {
      // 静默处理错误，避免触发刷新循环
      console.error('获取登录配置失败:', error);
      setOauthEnabled(false);
      setProviders([]);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = (providerId: string) => {
    const url = authService.getOAuthLoginUrl(providerId);
    window.location.href = url;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <Spin size="large" />
      </div>
    );
  }

  if (!oauthEnabled || providers.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <Card title="登录" style={{ width: 400 }}>
          <p className="text-gray-500">
            OAuth2 登录未配置或未启用。请在 设置 → 系统配置 中配置 OAuth2 提供商。
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <Card title="登录" style={{ width: 400 }}>
        {errorMsg && (
          <Alert
            type={errorCode === 'user_disabled' ? 'error' : 'warning'}
            message={errorMsg}
            showIcon
            className="mb-4"
          />
        )}
        <p className="mb-4 text-gray-600">请选择登录方式</p>
        <div className="space-y-3">
          {providers.map((p) => (
            <Button
              key={p.id}
              type="primary"
              block
              size="large"
              icon={p.type === 'github' ? <GithubOutlined /> : <LoginOutlined />}
              onClick={() => handleLogin(p.id)}
            >
              {p.type === 'github' ? '使用 GitHub 登录' : `使用 ${p.id} 登录`}
            </Button>
          ))}
        </div>
      </Card>
    </div>
  );
}
