import styled from 'styled-components';

export const ReportContainer = styled.div`
  border-radius: 11px;
  background-color: #fff;
  box-shadow: 0 2px 6px 0 #000a1a08;
  padding: 14px 20px;
  position: relative;
  overflow: hidden;
  width: 400px;
  background-image: url('https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*AnNuRJzJj3MAAAAAQlAAAAgAeprcAQ/original'),
    linear-gradient(180deg, #ffffff 0%, #ffffff00 100%);
  background-repeat: no-repeat;
  background-position: top center;
  background-size: 100%;
`;
export const ExportContainer = styled.div`
  margin-top: 8px;
  .export-list {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 4px;
    cursor: pointer;
  }
  .yuque-item {
    background: #ffffff;
    box-shadow: 0 2px 6px 0 #000a1a08;
    border-radius: 16px;
    padding: 6px 16px;
  }
  .yuque-icon {
    width: 18px;
    height: 18px;
    margin-right: 6px;
    vertical-align: -4px;
    display: inline-block;
  }
`;
export const ContentWrapper = styled.div`
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
`;
export const ReportTitle = styled.div`
  font-size: 15px;
  color: #000a1ae3;
  line-height: 24px;
  font-weight: 600;
  flex: 1;
  overflow: hidden;
  .report-title {
    display: flex;
    align-items: center;
  }
  .title-text {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .description {
    font-size: 12px;
    color: #000a1aad;
    line-height: 20px;
    text-align: justify;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .yuque-icon {
    width: 18px;
    height: 18px;
    margin-right: 6px;
    vertical-align: -3px;
    display: inline-block;
    flex-shrink: 0;
  }
`;
