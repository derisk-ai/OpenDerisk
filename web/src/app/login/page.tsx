'use client';

import { authService, OAuthProvider } from '@/services/auth';
import { STORAGE_USERINFO_KEY, STORAGE_USERINFO_VALID_TIME_KEY } from '@/utils/constants/index';
import { GithubOutlined, ThunderboltOutlined, UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { Alert, Button, Input, Spin } from 'antd';
import Image from 'next/image';
import { useSearchParams, useRouter } from 'next/navigation';
import { useEffect, useRef, useState, useCallback } from 'react';

const ERROR_MESSAGES: Record<string, string> = {
  user_disabled: 'Your account has been disabled. Please contact the administrator.',
  missing_params: 'OAuth callback parameters missing. Please try again.',
  invalid_state: 'OAuth state verification failed. Please try again.',
  token_exchange_failed: 'Failed to obtain OAuth token. Please try again.',
  userinfo_failed: 'Failed to fetch user information. Please try again.',
  user_create_failed: 'Failed to create user. Please contact the administrator.',
};

function ProviderIcon({ type }: { type: string }) {
  if (type === 'github') return <GithubOutlined style={{ fontSize: 18 }} />;
  if (type === 'alibaba-inc') return <ThunderboltOutlined style={{ fontSize: 18 }} />;
  return <UserOutlined style={{ fontSize: 18 }} />;
}

function providerLabel(p: OAuthProvider): string {
  if (p.type === 'github') return 'GitHub';
  if (p.type === 'alibaba-inc') return 'Alibaba';
  if (p.type === 'local') return '';
  return p.id;
}

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState<OAuthProvider[]>([]);
  const [oauthEnabled, setOauthEnabled] = useState(false);
  const loadedRef = useRef(false);
  const searchParams = useSearchParams();
  const errorCode = searchParams?.get('error') || '';
  const errorMsg = errorCode ? ERROR_MESSAGES[errorCode] || `Login error: ${errorCode}` : '';

  // Local auth state
  const [isLocalMode, setIsLocalMode] = useState(false);
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [email, setEmail] = useState('');
  const [localError, setLocalError] = useState('');
  const [submitting, setSubmitting] = useState(false);

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
      const nonLocal = (status.providers || []).filter(p => p.type !== 'local');
      if (status.enabled && nonLocal.length === 0) {
        setIsLocalMode(true);
      }
    } catch {
      setOauthEnabled(false);
      setProviders([]);
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthLogin = (providerId: string) => {
    window.location.href = authService.getOAuthLoginUrl(providerId);
  };

  const saveUserAndRedirect = useCallback(async () => {
    try {
      const me = await authService.getMe();
      const user = {
        user_channel: me.user_channel,
        user_no: me.user_no,
        nick_name: me.nick_name,
        avatar_url: me.avatar_url || me.user?.avatar || '',
        email: me.email || me.user?.email || '',
        role: me.role || 'normal',
      };
      localStorage.setItem(STORAGE_USERINFO_KEY, JSON.stringify(user));
      localStorage.setItem(STORAGE_USERINFO_VALID_TIME_KEY, Date.now().toString());
    } catch { /* will be loaded by layout */ }
    const nextRaw = searchParams?.get('next') || '/';
    let next = '/';
    try {
      const decoded = decodeURIComponent(nextRaw);
      if (decoded.startsWith('/') && !decoded.startsWith('/login')) next = decoded;
    } catch {
      next = '/';
    }
    router.replace(next);
  }, [router, searchParams]);

  const handleLocalLogin = async () => {
    setLocalError('');
    if (!username.trim() || !password) {
      setLocalError('Please enter username and password');
      return;
    }
    setSubmitting(true);
    try {
      await authService.localLogin({ username: username.trim(), password });
      await saveUserAndRedirect();
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.response?.data?.err_msg;
      setLocalError(typeof detail === 'string' && detail ? detail : 'Login failed. Please check your credentials.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleLocalRegister = async () => {
    setLocalError('');
    if (!username.trim() || username.trim().length < 3) {
      setLocalError('Username must be at least 3 characters');
      return;
    }
    if (!password || password.length < 6) {
      setLocalError('Password must be at least 6 characters');
      return;
    }
    if (password !== confirmPassword) {
      setLocalError('Passwords do not match');
      return;
    }
    setSubmitting(true);
    try {
      await authService.localRegister({
        username: username.trim(),
        password,
        email: email.trim() || undefined,
      });
      await saveUserAndRedirect();
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.response?.data?.err_msg;
      setLocalError(typeof detail === 'string' && detail ? detail : 'Registration failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !submitting) {
      isRegister ? handleLocalRegister() : handleLocalLogin();
    }
  };

  if (loading) {
    return (
      <div className='flex items-center justify-center min-h-screen bg-[#FAFAFA]'>
        <Spin size='large' />
      </div>
    );
  }

  const oauthProviders = providers.filter(p => p.type !== 'local');
  const hasLocal = providers.some(p => p.type === 'local');

  return (
    <div className='relative flex items-center justify-center min-h-screen bg-[#FAFAFA] overflow-hidden'>
      {/* Decorative background elements */}
      <div className='pointer-events-none absolute inset-0'>
        <div className='absolute top-[-120px] right-[-80px] w-[400px] h-[400px] rounded-full'
          style={{ background: 'radial-gradient(circle, rgba(0,200,220,0.08) 0%, transparent 70%)' }} />
        <div className='absolute bottom-[-100px] left-[-60px] w-[350px] h-[350px] rounded-full'
          style={{ background: 'radial-gradient(circle, rgba(0,120,255,0.06) 0%, transparent 70%)' }} />
        <div className='absolute top-[30%] left-[10%] w-[200px] h-[200px] rounded-full'
          style={{ background: 'radial-gradient(circle, rgba(0,220,180,0.04) 0%, transparent 70%)' }} />
      </div>

      <div className='relative z-10 w-full max-w-[400px] mx-4'>
        {/* Logo */}
        <div className='flex justify-center mb-8'>
          <Image
            src='/logo_zh_latest.png'
            alt='DeRisk'
            width={160}
            height={42}
            className='h-[42px] w-auto'
            priority
          />
        </div>

        {/* Main card */}
        <div className='bg-white rounded-xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)] border border-gray-100/80 px-7 py-7'>
          {errorMsg && (
            <Alert
              type={errorCode === 'user_disabled' ? 'error' : 'warning'}
              message={errorMsg}
              showIcon
              className='mb-4 rounded-lg'
            />
          )}

          {!oauthEnabled ? (
            <div className='text-center py-6'>
              <p className='text-gray-400 text-sm leading-relaxed'>
                Login is not configured.<br />
                Please enable OAuth2 or access control plugin in System Settings.
              </p>
            </div>
          ) : isLocalMode ? (
            /* ─── Local login / register form ─── */
            <div>
              <div className='flex items-center justify-between mb-5'>
                <h2 className='text-[17px] font-semibold text-gray-800 tracking-tight'>
                  {isRegister ? 'Create Account' : 'Sign In'}
                </h2>
                {oauthProviders.length > 0 && (
                  <button
                    onClick={() => setIsLocalMode(false)}
                    className='text-xs text-gray-400 hover:text-[#0C75FC] transition-colors'
                  >
                    More options
                  </button>
                )}
              </div>

              {localError && (
                <Alert type='error' message={localError} showIcon className='mb-4 rounded-lg' closable onClose={() => setLocalError('')} />
              )}

              <div className='space-y-3'>
                <Input
                  size='large'
                  prefix={<UserOutlined className='text-gray-300' />}
                  placeholder='Username'
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className='rounded-lg'
                  style={{ height: 42 }}
                />
                <Input.Password
                  size='large'
                  prefix={<LockOutlined className='text-gray-300' />}
                  placeholder='Password'
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className='rounded-lg'
                  style={{ height: 42 }}
                />
                {isRegister && (
                  <>
                    <Input.Password
                      size='large'
                      prefix={<LockOutlined className='text-gray-300' />}
                      placeholder='Confirm Password'
                      value={confirmPassword}
                      onChange={e => setConfirmPassword(e.target.value)}
                      onKeyDown={handleKeyDown}
                      className='rounded-lg'
                      style={{ height: 42 }}
                    />
                    <Input
                      size='large'
                      prefix={<MailOutlined className='text-gray-300' />}
                      placeholder='Email (optional)'
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      onKeyDown={handleKeyDown}
                      className='rounded-lg'
                      style={{ height: 42 }}
                    />
                  </>
                )}

                <Button
                  type='primary'
                  block
                  size='large'
                  loading={submitting}
                  onClick={isRegister ? handleLocalRegister : handleLocalLogin}
                  className='rounded-lg font-medium'
                  style={{ height: 42, background: '#0C75FC' }}
                >
                  {isRegister ? 'Create Account' : 'Sign In'}
                </Button>
              </div>

              <div className='mt-4 text-center'>
                <button
                  className='text-[13px] text-gray-400 hover:text-[#0C75FC] transition-colors'
                  onClick={() => {
                    setIsRegister(!isRegister);
                    setLocalError('');
                    setConfirmPassword('');
                  }}
                >
                  {isRegister ? 'Already have an account? Sign in' : "Don't have an account? Register"}
                </button>
              </div>

              {/* OAuth provider icons */}
              {oauthProviders.length > 0 && (
                <>
                  <div className='flex items-center my-5'>
                    <div className='flex-1 h-px bg-gray-100' />
                    <span className='px-3 text-[11px] text-gray-300 uppercase tracking-widest'>or</span>
                    <div className='flex-1 h-px bg-gray-100' />
                  </div>
                  <div className='flex justify-center gap-3'>
                    {oauthProviders.map(p => (
                      <button
                        key={p.id}
                        onClick={() => handleOAuthLogin(p.id)}
                        className='flex items-center justify-center w-10 h-10 rounded-lg border border-gray-100 bg-gray-50/60 hover:bg-gray-100 hover:border-gray-200 transition-all text-gray-400 hover:text-gray-600'
                        title={`Sign in with ${providerLabel(p)}`}
                      >
                        <ProviderIcon type={p.type} />
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          ) : (
            /* ─── Provider selection ─── */
            <div>
              <h2 className='text-[17px] font-semibold text-gray-800 mb-5 tracking-tight'>Sign In</h2>

              <div className='space-y-2.5'>
                {oauthProviders.map(p => (
                  <button
                    key={p.id}
                    onClick={() => handleOAuthLogin(p.id)}
                    className='flex items-center w-full h-[42px] px-4 rounded-lg border border-gray-100 bg-white hover:bg-gray-50 hover:border-gray-200 transition-all group'
                  >
                    <span className='text-gray-400 group-hover:text-gray-600 transition-colors'>
                      <ProviderIcon type={p.type} />
                    </span>
                    <span className='ml-3 text-[13px] font-medium text-gray-600 group-hover:text-gray-800 transition-colors'>
                      Continue with {providerLabel(p)}
                    </span>
                  </button>
                ))}

                {hasLocal && (
                  <>
                    {oauthProviders.length > 0 && (
                      <div className='flex items-center my-2.5'>
                        <div className='flex-1 h-px bg-gray-100' />
                        <span className='px-3 text-[11px] text-gray-300 uppercase tracking-widest'>or</span>
                        <div className='flex-1 h-px bg-gray-100' />
                      </div>
                    )}
                    <button
                      onClick={() => setIsLocalMode(true)}
                      className='flex items-center w-full h-[42px] px-4 rounded-lg border border-gray-100 bg-white hover:bg-gray-50 hover:border-gray-200 transition-all group'
                    >
                      <span className='text-gray-400 group-hover:text-gray-600 transition-colors'>
                        <LockOutlined style={{ fontSize: 18 }} />
                      </span>
                      <span className='ml-3 text-[13px] font-medium text-gray-600 group-hover:text-gray-800 transition-colors'>
                        Sign in with Username
                      </span>
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className='text-center mt-6 text-[11px] text-gray-300 tracking-wide'>
          Powered by DeRisk
        </p>
      </div>
    </div>
  );
}
