import { ChatEn } from './chat';
import { CommonEn } from './common';
import { FlowEn } from './flow';
import { PermissionsEn } from './permissions';

const en = {
  ...ChatEn,
  ...FlowEn,
  ...CommonEn,
  ...PermissionsEn,
};

export default en;
