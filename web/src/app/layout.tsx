"use client";
import { ChatContext, ChatContextProvider } from "@/contexts";
import { InteractionProvider } from "@/components/interaction";
import SideBar from "@/components/layout/side-bar";
import TopHeader from "@/components/layout/top-header";
import FloatHelper from "@/components/layout/float-helper";
import {
  STORAGE_LANG_KEY,
  STORAGE_USERINFO_KEY,
  STORAGE_USERINFO_VALID_TIME_KEY,
} from "@/utils/constants/index";
import { App, ConfigProvider, MappingAlgorithm, Spin, theme } from "antd";
import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import Head from "next/head";
import React, { useContext, useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { usePathname } from "next/navigation";
import "./i18n";
import "../styles/globals.css";
import { Suspense } from 'react'
import { authService } from "@/services/auth";

// Prevent SSR flash
const EmptyLayout = ({ children }: { children: React.ReactNode }) => <>{children}</>;

const antdDarkTheme: MappingAlgorithm = (seedToken, mapToken) => {
  return {
    ...theme.darkAlgorithm(seedToken, mapToken),
    colorBgBase: "#232734",
    colorBorder: "#828282",
    colorBgContainer: "#232734",
  };
};

function CssWrapper({ children }: { children: React.ReactElement }) {
  const { mode } = useContext(ChatContext);
  const { i18n } = useTranslation();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mode) {
      document.body?.classList?.add(mode);
      if (mode === "light") {
        document.body?.classList?.remove("dark");
      } else {
        document.body?.classList?.remove("light");
      }
    }
  }, [mode]);

  useEffect(() => {
    if (mounted) {
      i18n.changeLanguage?.(
        window.localStorage.getItem(STORAGE_LANG_KEY) || "zh"
      );
    }
  }, [i18n, mounted]);

  if (!mounted) return <>{children}</>;

  return <div>{children}</div>;
}

function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const { mode } = useContext(ChatContext);
  const { i18n } = useTranslation();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const authCheckInProgress = useRef(false);

  const isPublicRoute = pathname?.startsWith("/login") || pathname?.startsWith("/auth/callback");

  useEffect(() => {
    setMounted(true);
  }, []);

  // 非阻塞：后台校验 OAuth，若开启且未登录则跳转。OAuth 关闭时用 mock；OAuth 开启且未登录时再跳转
  useEffect(() => {
    if (!mounted || isPublicRoute || authCheckInProgress.current) return;

    const checkAuth = async () => {
      authCheckInProgress.current = true;
      try {
        const oauthStatus = await authService.getOAuthStatus();
        if (!oauthStatus.enabled) {
          const user = { user_channel: "derisk", user_no: "001", nick_name: "derisk" };
          localStorage.setItem(STORAGE_USERINFO_KEY, JSON.stringify(user));
          localStorage.setItem(STORAGE_USERINFO_VALID_TIME_KEY, Date.now().toString());
          return;
        }
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
      } catch {
        try {
          const oauthStatus = await authService.getOAuthStatus();
          if (oauthStatus.enabled) {
            // 避免已经在登录页面时重复跳转
            const currentPath = window.location.pathname;
            if (!currentPath.startsWith("/login") && !currentPath.startsWith("/auth/callback")) {
              window.location.href = "/login";
            }
            return;
          }
        } catch {
          /* ignore */
        }
        const user = { user_channel: "derisk", user_no: "001", nick_name: "derisk" };
        localStorage.setItem(STORAGE_USERINFO_KEY, JSON.stringify(user));
        localStorage.setItem(STORAGE_USERINFO_VALID_TIME_KEY, Date.now().toString());
      } finally {
        authCheckInProgress.current = false;
      }
    };
    checkAuth();
  }, [mounted]); // 只依赖 mounted，pathname 变化不重新检查

  // 公开页面：直接渲染（无侧边栏）
  if (isPublicRoute) {
    return (
      <ConfigProvider
        locale={i18n.language === "en" ? enUS : zhCN}
        theme={{ token: { colorPrimary: "#0C75FC", borderRadius: 4 }, algorithm: undefined }}
      >
        <App>{children}</App>
      </ConfigProvider>
    );
  }

  const renderContent = () => {
    return (
      <div className="flex w-screen h-screen overflow-hidden">
        <Head>
          <meta
            name="viewport"
            content="initial-scale=1.0, width=device-width, maximum-scale=1"
          />
        </Head>
        <div className="transition-[width] duration-300 ease-in-out h-full flex flex-col">
          <SideBar />
        </div>
        <div className="flex flex-col flex-1 relative overflow-hidden">
          <TopHeader />
          {children}
        </div>
        <FloatHelper />
      </div>
    );
  };

  return (
    <ConfigProvider
      locale={i18n.language === "en" ? enUS : zhCN}
      theme={{
        token: {
          colorPrimary: "#0C75FC",
          borderRadius: 4,
        },
        // algorithm: mode === "dark" ? antdDarkTheme : undefined,
        // 暂不支持 dark 
        algorithm: undefined,
      }}
    >
      <App>{renderContent()}</App>
    </ConfigProvider>
  );
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning data-theme="light" className="light">
      <body suppressHydrationWarning={true} className="bg-[#FAFAFA] dark:bg-[#111]">
        <Suspense fallback={
          <App className="w-screen h-screen flex items-center justify-center">
            <Spin />
          </App>
          }>
          <ChatContextProvider>
            <InteractionProvider autoConnect={false}>
              <CssWrapper>
                <LayoutWrapper>{children}</LayoutWrapper>
              </CssWrapper>
            </InteractionProvider>
          </ChatContextProvider>
        </Suspense>
      </body>
    </html>
  );
}
