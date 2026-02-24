import { Segmented, Tabs } from 'antd';
import { isEqual, set } from 'lodash';
import React, { useEffect, useState } from 'react';
import Code from './Code';
import { VisCodeIdeDiv, VisPureCode } from './style';

interface Props {
  pureCode?: boolean;
  items?: TS.CodeIde[];
}

const VisCodeIde = ({ items = [], pureCode = false }: Props) => {
  const [tabIndex, setTabIndex] = useState<number>(0);
  const currentCode = items?.[tabIndex];
  const currentIsHTML = currentCode?.language === 'html';
  const [showTypeList, setShowTypeList] = useState<
    Array<'html-preview' | 'code-with-console' | 'code'>
  >(items.map(() => 'code'));

  const currentType = showTypeList[tabIndex];

  useEffect(() => {
    const codeContent = currentCode?.markdown || '';
    if (currentIsHTML && codeContent.trimEnd().endsWith('</html>')) {
      setShowTypeList((v) => [...set(v, tabIndex, 'html-preview')]);
    } else if (currentCode?.console?.length) {
      setShowTypeList((v) => [...set(v, tabIndex, 'code-with-console')]);
    }
  }, [currentCode, currentIsHTML, tabIndex]);

  const changeType = currentIsHTML && (
    <Segmented
      value={currentType}
      onChange={(v) => {
        setShowTypeList([...set(showTypeList, tabIndex, v)]);
      }}
      options={[
        { label: '代码', value: 'code' },
        { label: '预览', value: 'html-preview' },
      ]}
    />
  );

  if (pureCode) {
    // 没有 console
    return (
      <VisCodeIdeDiv className="vis-code-ide-code">
        <VisPureCode className="vis-pure-code">
          <>{changeType}</>
          {items.map((item, index) => {
            const showType = showTypeList[index];
            return <Code showType={showType} key={index} {...item} />;
          })}
        </VisPureCode>
      </VisCodeIdeDiv>
    );
  }

  return (
    <>
      <VisCodeIdeDiv className="vis-code-ide scrollbar-default">
        <Tabs
          defaultActiveKey={`${tabIndex}`}
          onChange={(i) => {
            setTabIndex(parseInt(i));
          }}
          tabBarStyle={{
            marginBottom: 0,
          }}
          tabBarExtraContent={{
            right: changeType,
          }}
          items={items.map((item, i) => {
            const showType = showTypeList[i];
            return {
              label: item?.path,
              key: `${i}`,
              children: (
                <>
                  <Code key={i} {...item} showType={showType} />
                </>
              ),
            };
          })}
        />
      </VisCodeIdeDiv>
    </>
  );
};

export default React.memo(VisCodeIde, isEqual);
