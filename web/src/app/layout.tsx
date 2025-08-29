"use client";
import { ChatContext, ChatContextProvider } from "@/contexts";
import SideBar from "@/components/layout/side-bar";
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
import React, { useContext, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import "./i18n";
import "../styles/globals.css";
import { Suspense } from 'react'
import '@ant-design/v5-patch-for-react-19';

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
    i18n.changeLanguage?.(
      window.localStorage.getItem(STORAGE_LANG_KEY) || "zh"
    );
  }, [i18n]);

  return <div>{children}</div>;
}

function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const { mode } = useContext(ChatContext);
  const { i18n } = useTranslation();
  const [isLogin, setIsLogin] = useState(false);

  // 登录检测
  const handleAuth = async () => {
    // MOCK User info
    const user = {
      user_channel: `derisk`,
      user_no: `001`,
      nick_name: `derisk`,
    };
    if (user) {
      localStorage.setItem(STORAGE_USERINFO_KEY, JSON.stringify(user));
      localStorage.setItem(
        STORAGE_USERINFO_VALID_TIME_KEY,
        Date.now().toString()
      );
      setIsLogin(true);
    }
  };

  useEffect(() => {
    handleAuth();
  }, []);

  if (!isLogin) {
    return null;
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
      <body suppressHydrationWarning={true}>
        <Suspense fallback={
          <App className="w-screen h-screen flex items-center justify-center">
            <Spin />
          </App>
          }>
          <ChatContextProvider>
            <CssWrapper>
              <LayoutWrapper>{children}</LayoutWrapper>
            </CssWrapper>
          </ChatContextProvider>
        </Suspense>
      </body>
    </html>
  );
}
