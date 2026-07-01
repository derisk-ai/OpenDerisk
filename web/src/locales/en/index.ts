import { ChatEn } from './chat';
import { CommonEn } from './common';
import { FlowEn } from './flow';
import { PermissionsEn } from './permissions';
import { WorkspacesEn } from './workspaces';

const en = {
  ...ChatEn,
  ...FlowEn,
  ...CommonEn,
  ...PermissionsEn,
  ...WorkspacesEn,
};

export default en;
