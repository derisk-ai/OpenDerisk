-- You can change `derisk` to your actual metadata database name in your `.env` file
-- eg. `LOCAL_DB_NAME=derisk`

CREATE
DATABASE IF NOT EXISTS derisk;
use derisk;

-- ============================================================
-- MySQL DDL Script for Derisk
-- Version: 0.3.0
-- Generated from SQLAlchemy ORM Models
-- Generated: 2026-04-11 13:47:09
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- Table: derisk_cluster_registry_instance
-- Source Model: ModelInstanceEntity
CREATE TABLE IF NOT EXISTS `derisk_cluster_registry_instance` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `model_name` VARCHAR(128) NOT NULL COMMENT 'Model name',
  `host` VARCHAR(128) NOT NULL COMMENT 'Host of the model',
  `port` INT NOT NULL COMMENT 'Port of the model',
  `weight` FLOAT NULL COMMENT 'Weight of the model',
  `check_healthy` TINYINT(1) NULL DEFAULT 1 COMMENT 'Whether to check the health of the model',
  `healthy` TINYINT(1) NULL DEFAULT 0 COMMENT 'Whether the model is healthy',
  `enabled` TINYINT(1) NULL DEFAULT 1 COMMENT 'Whether the model is enabled',
  `prompt_template` VARCHAR(128) NULL COMMENT 'Prompt template for the model instance',
  `last_heartbeat` DATETIME NULL COMMENT 'Last heartbeat time of the model instance',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_model_instance` (`model_name`, `host`, `port`, `sys_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: streaming_tool_config
-- Source Model: StreamingToolConfig
CREATE TABLE IF NOT EXISTS `streaming_tool_config` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `app_code` VARCHAR(128) NOT NULL COMMENT '应用代码',
  `tool_name` VARCHAR(128) NOT NULL COMMENT '工具名称',
  `tool_display_name` VARCHAR(256) NULL COMMENT '工具显示名称',
  `tool_description` TEXT NULL COMMENT '工具描述',
  `param_configs` JSON NOT NULL COMMENT '参数配置',
  `global_threshold` INT NULL DEFAULT 256 COMMENT '全局阈值',
  `global_strategy` VARCHAR(32) NULL COMMENT '全局策略',
  `global_renderer` VARCHAR(32) NULL COMMENT '全局渲染器',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用流式',
  `priority` INT NOT NULL DEFAULT 0 COMMENT '优先级',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_by` VARCHAR(128) NULL COMMENT '创建人',
  `updated_by` VARCHAR(128) NULL COMMENT '更新人',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_history
-- Source Model: ChatHistoryEntity
CREATE TABLE IF NOT EXISTS `chat_history` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_uid` VARCHAR(255) NOT NULL COMMENT 'Conversation record unique id',
  `chat_mode` VARCHAR(255) NOT NULL COMMENT 'Conversation scene mode',
  `summary` LONGTEXT NOT NULL COMMENT 'Conversation record summary',
  `user_name` VARCHAR(255) NULL COMMENT 'interlocutor',
  `messages` LONGTEXT NULL COMMENT 'Conversation details',
  `message_ids` LONGTEXT NULL COMMENT 'Message ids, split by comma',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `app_code` VARCHAR(255) NULL COMMENT 'App unique code',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conv_uid` (`conv_uid`),
  KEY `idx_q_user` (`user_name`),
  KEY `idx_q_mode` (`chat_mode`),
  KEY `idx_q_conv` (`summary`),
  KEY `idx_chat_his_app_code` (`app_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_history_message
-- Source Model: ChatHistoryMessageEntity
CREATE TABLE IF NOT EXISTS `chat_history_message` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_uid` VARCHAR(255) NOT NULL COMMENT 'Conversation record unique id',
  `index` INT NOT NULL COMMENT 'Message index',
  `round_index` INT NOT NULL COMMENT 'Message round index',
  `message_detail` LONGTEXT NULL COMMENT 'Message details, json format',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conversation_message` (`conv_uid`, `index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: user
-- Source Model: User
CREATE TABLE IF NOT EXISTS `user` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(50) NULL,
  `fullname` VARCHAR(50) NULL,
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: recommend_question
-- Source Model: RecommendQuestionEntity
CREATE TABLE IF NOT EXISTS `recommend_question` (
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: agent_input_queue
-- Source Model: AgentInputQueueEntity
CREATE TABLE IF NOT EXISTS `agent_input_queue` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `conv_id` VARCHAR(255) NOT NULL COMMENT '对话ID (agent_conv_id)',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT '会话ID',
  `message_id` VARCHAR(64) NOT NULL COMMENT '消息唯一ID',
  `message_content` TEXT NOT NULL COMMENT '消息内容 (JSON)',
  `sender_name` VARCHAR(128) NULL COMMENT '发送者名称',
  `sender_type` VARCHAR(32) NULL COMMENT '发送者类型 (user/system)',
  `status` VARCHAR(20) NOT NULL COMMENT 'pending/processing/consumed',
  `consumed_at` DATETIME NULL COMMENT '消费时间',
  `consumed_by` VARCHAR(64) NULL COMMENT '消费的服务器实例ID',
  `priority` INT NULL DEFAULT 0 COMMENT '优先级 (数字越大越优先)',
  `extra` TEXT NULL COMMENT '扩展信息 (JSON)',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_input_conv_session_status` (`conv_session_id`, `status`),
  KEY `idx_input_conv_id_status` (`conv_id`, `status`),
  KEY `idx_input_gmt_create` (`gmt_create`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: authorization_audit_log
-- Source Model: AuthorizationAuditLogEntity
CREATE TABLE IF NOT EXISTS `authorization_audit_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `session_id` VARCHAR(255) NOT NULL COMMENT 'Session identifier',
  `user_id` VARCHAR(255) NULL COMMENT 'User identifier',
  `agent_name` VARCHAR(255) NULL COMMENT 'Agent name',
  `tool_name` VARCHAR(255) NOT NULL COMMENT 'Tool name',
  `arguments` TEXT NULL COMMENT 'Tool arguments (JSON)',
  `decision` VARCHAR(32) NOT NULL COMMENT 'Authorization decision',
  `action` VARCHAR(16) NOT NULL COMMENT 'Permission action',
  `reason` TEXT NULL COMMENT 'Reason for the decision',
  `risk_level` VARCHAR(16) NULL COMMENT 'Risk level',
  `risk_score` INT NULL COMMENT 'Risk score (0-100)',
  `risk_factors` TEXT NULL COMMENT 'Risk factors (JSON array)',
  `cached` INT NOT NULL DEFAULT 0 COMMENT 'Whether from cache',
  `duration_ms` FLOAT NOT NULL COMMENT 'Duration in milliseconds',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When the audit log was created',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_audit_session` (`session_id`),
  KEY `idx_audit_tool` (`tool_name`),
  KEY `idx_audit_decision` (`decision`),
  KEY `idx_audit_risk_level` (`risk_level`),
  KEY `idx_audit_created_at` (`created_at`),
  KEY `idx_audit_user` (`user_id`),
  KEY `idx_audit_agent` (`agent_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: user_recent_apps
-- Source Model: UserRecentAppsEntity
CREATE TABLE IF NOT EXISTS `user_recent_apps` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `app_code` VARCHAR(255) NOT NULL COMMENT 'Current AI assistant code',
  `user_code` VARCHAR(255) NULL COMMENT 'user code',
  `sys_code` VARCHAR(255) NULL COMMENT 'system app code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `last_accessed` DATETIME NULL COMMENT 'last access time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_r_app_code` (`app_code`),
  KEY `idx_user_code` (`user_code`),
  KEY `idx_last_accessed` (`last_accessed`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_conversations
-- Source Model: GptsConversationsEntity
CREATE TABLE IF NOT EXISTS `gpts_conversations` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `user_goal` TEXT NOT NULL COMMENT 'User',
  `gpts_name` VARCHAR(255) NOT NULL COMMENT 'The gpts name',
  `team_mode` VARCHAR(255) NOT NULL COMMENT 'The conversation team mode',
  `state` VARCHAR(255) NULL COMMENT 'The gpts state',
  `max_auto_reply_round` INT NOT NULL COMMENT 'max auto reply round',
  `auto_reply_count` INT NOT NULL COMMENT 'auto reply count',
  `user_code` VARCHAR(255) NULL COMMENT 'user code',
  `sys_code` VARCHAR(255) NULL COMMENT 'system app ',
  `vis_render` VARCHAR(255) NULL COMMENT 'vis mode of chat conversation ',
  `extra` TEXT NULL COMMENT 'the extra info of the conversation',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gpts_conversations` (`conv_id`),
  KEY `idx_gpts_name` (`gpts_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_file_metadata
-- Source Model: GptsFileMetadataEntity
CREATE TABLE IF NOT EXISTS `gpts_file_metadata` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT 'The session id within conversation',
  `file_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the file',
  `file_key` VARCHAR(512) NOT NULL COMMENT 'The key of the file in file system',
  `file_name` VARCHAR(512) NOT NULL COMMENT 'The name of the file',
  `file_type` VARCHAR(64) NOT NULL COMMENT 'The type of the file',
  `file_size` INT NOT NULL DEFAULT 0 COMMENT 'The size of file in bytes',
  `local_path` VARCHAR(1024) NOT NULL COMMENT 'The local path of the file',
  `oss_url` VARCHAR(1024) NULL COMMENT 'The OSS URL of the file',
  `preview_url` VARCHAR(1024) NULL COMMENT 'The preview URL of the file',
  `download_url` VARCHAR(1024) NULL COMMENT 'The download URL of the file',
  `content_hash` VARCHAR(128) NULL COMMENT 'The content hash for deduplication',
  `status` VARCHAR(32) NOT NULL COMMENT 'Status: pending/uploading/completed/failed/expired',
  `mime_type` VARCHAR(128) NULL COMMENT 'The MIME type of the file',
  `is_public` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether the file is public',
  `created_by` VARCHAR(255) NULL COMMENT 'The agent name that created this file',
  `task_id` VARCHAR(255) NULL COMMENT 'The related task id',
  `message_id` VARCHAR(255) NULL COMMENT 'The related message id',
  `tool_name` VARCHAR(255) NULL COMMENT 'The related tool name',
  `metadata` TEXT NULL COMMENT 'Additional metadata (JSON)',
  `expires_at` DATETIME NULL COMMENT 'The expiration time',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_file_meta_conv_session` (`conv_id`, `conv_session_id`),
  KEY `idx_file_meta_file_key` (`conv_id`, `file_key`),
  KEY `idx_file_meta_file_type` (`conv_id`, `file_type`),
  KEY `idx_file_catalog_conv` (`conv_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_file_catalog
-- Source Model: GptsFileCatalogEntity
CREATE TABLE IF NOT EXISTS `gpts_file_catalog` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation',
  `file_key` VARCHAR(512) NOT NULL COMMENT 'The key of the file in file system',
  `file_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the file',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_file_catalog_conv` (`conv_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_kanban
-- Source Model: GptsKanbanEntity
CREATE TABLE IF NOT EXISTS `gpts_kanban` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation',
  `session_id` VARCHAR(255) NOT NULL COMMENT 'The session id within conversation',
  `agent_id` VARCHAR(255) NOT NULL COMMENT 'The agent id that created this kanban',
  `kanban_id` VARCHAR(255) NOT NULL COMMENT 'Kanban unique id',
  `mission` TEXT NOT NULL COMMENT 'Mission description',
  `current_stage_index` INT NOT NULL DEFAULT 0 COMMENT 'Current stage index',
  `stages` LONGTEXT NULL COMMENT 'Stages data (JSON)',
  `deliverables` LONGTEXT NULL COMMENT 'Deliverables data (JSON)',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_kanban_conv_session` (`conv_id`, `session_id`),
  KEY `idx_pre_kanban_log_conv_session` (`conv_id`, `session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_pre_kanban_log
-- Source Model: GptsPreKanbanLogEntity
CREATE TABLE IF NOT EXISTS `gpts_pre_kanban_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation',
  `session_id` VARCHAR(255) NOT NULL COMMENT 'The session id within conversation',
  `agent_id` VARCHAR(255) NOT NULL COMMENT 'The agent id',
  `logs` LONGTEXT NULL COMMENT 'Pre-kanban logs (JSON)',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_pre_kanban_log_conv_session` (`conv_id`, `session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_messages
-- Source Model: GptsMessagesEntity
CREATE TABLE IF NOT EXISTS `gpts_messages` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `message_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the messages',
  `sender` VARCHAR(255) NOT NULL COMMENT 'Who(role) speaking in the current conversation turn',
  `sender_name` VARCHAR(255) NOT NULL COMMENT 'Who(name) speaking in the current conversation turn',
  `receiver` VARCHAR(255) NOT NULL COMMENT 'Who(role) receive message in the current conversation turn',
  `receiver_name` VARCHAR(255) NOT NULL COMMENT 'Who(name) receive message in the current conversation turn',
  `model_name` VARCHAR(255) NULL COMMENT 'message generate model',
  `rounds` INT NOT NULL COMMENT 'dialogue turns',
  `is_success` TINYINT(1) NULL DEFAULT 1 COMMENT 'is success',
  `app_code` VARCHAR(255) NOT NULL COMMENT 'The message in which app',
  `app_name` VARCHAR(255) NOT NULL COMMENT 'The message in which app name',
  `thinking` LONGTEXT NULL COMMENT 'Thinking of the speech',
  `content` LONGTEXT NULL COMMENT 'Content of the speech',
  `content_types` VARCHAR(1000) NULL COMMENT 'Content types of the speech',
  `message_type` VARCHAR(255) NULL COMMENT 'type of the message',
  `system_prompt` LONGTEXT NULL COMMENT 'this message system prompt',
  `user_prompt` LONGTEXT NULL COMMENT 'this message system prompt',
  `show_message` TINYINT(1) NULL COMMENT 'Whether the current message needs to be displayed to the user',
  `goal_id` VARCHAR(255) NULL COMMENT 'The target id to the current message',
  `current_goal` TEXT NULL COMMENT 'The target corresponding to the current message',
  `context` TEXT NULL COMMENT 'Current conversation context',
  `review_info` TEXT NULL COMMENT 'Current conversation review info',
  `action_report` LONGTEXT NULL COMMENT 'Current conversation action report',
  `resource_info` TEXT NULL COMMENT 'Current conversation resource info',
  `role` VARCHAR(255) NULL COMMENT 'The role of the current message content',
  `avatar` VARCHAR(255) NULL COMMENT 'The avatar of the agent who send current message content',
  `metrics` VARCHAR(1000) NULL COMMENT 'The performance metrics of agent messages',
  `tool_calls` LONGTEXT NULL COMMENT 'The tool_calls of agent messages',
  `input_tools` LONGTEXT NULL COMMENT 'The input tools passed to LLM',
  `observation` LONGTEXT NULL COMMENT 'The  message observation',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_q_messages` (`conv_id`, `rounds`, `sender`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_messages_system
-- Source Model: GptsMessagesSystemEntity
CREATE TABLE IF NOT EXISTS `gpts_messages_system` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modified` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'agent对话id',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT 'agent会话id',
  `conv_round_id` VARCHAR(255) NULL COMMENT 'agent会话轮次id',
  `agent` VARCHAR(255) NOT NULL COMMENT '消息所属Agent',
  `type` VARCHAR(255) NOT NULL COMMENT '消息类型(error 运行异常, notify 运行通知)',
  `phase` VARCHAR(255) NOT NULL COMMENT '消息阶段(in_context, llm_call, action_run, message_out)',
  `agent_message_id` VARCHAR(255) NOT NULL COMMENT '关联的Agent消息id',
  `message_id` VARCHAR(255) NOT NULL COMMENT '消息id',
  `content` TEXT NULL COMMENT '消息内容',
  `content_extra` VARCHAR(2000) NULL COMMENT '消息扩展内容，根据类型阶段不同，内容不同',
  `retry_time` SMALLINT NULL DEFAULT 0 COMMENT '当前阶段重试次数',
  `final_status` VARCHAR(20) NULL COMMENT '当前阶段最终状态',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_message_phase` (`conv_id`, `phase`),
  KEY `idx_message_type` (`conv_id`, `type`, `phase`),
  KEY `idx_agent_message` (`conv_id`, `agent_message_id`),
  KEY `idx_message` (`message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_plans
-- Source Model: GptsPlansEntity
CREATE TABLE IF NOT EXISTS `gpts_plans` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation session',
  `task_uid` VARCHAR(255) NOT NULL COMMENT 'The uid of the plan task',
  `sub_task_num` INT NOT NULL COMMENT 'Subtask id',
  `conv_round` INT NOT NULL COMMENT 'The dialogue turns',
  `conv_round_id` VARCHAR(255) NULL COMMENT 'The dialogue turns uid',
  `sub_task_id` VARCHAR(255) NOT NULL COMMENT 'Subtask id',
  `task_parent` VARCHAR(255) NULL COMMENT 'Subtask parent task id',
  `sub_task_title` VARCHAR(255) NOT NULL COMMENT 'subtask title',
  `sub_task_content` TEXT NOT NULL COMMENT 'subtask content',
  `sub_task_agent` VARCHAR(255) NULL COMMENT 'Available agents corresponding to subtasks',
  `resource_name` VARCHAR(255) NULL COMMENT 'resource name',
  `agent_model` VARCHAR(255) NULL COMMENT 'LLM model used by subtask processing agents',
  `retry_times` INT NULL DEFAULT 0 COMMENT 'number of retries',
  `max_retry_times` INT NULL DEFAULT 0 COMMENT 'Maximum number of retries',
  `state` VARCHAR(255) NULL COMMENT 'subtask status',
  `result` TEXT NULL COMMENT 'subtask result',
  `task_round_title` VARCHAR(255) NULL COMMENT 'task round title.(Can be empty if there are no multiple tasks in a round)',
  `task_round_description` VARCHAR(500) NULL COMMENT 'task round description.(Can be empty if there are no multiple tasks in a round)',
  `planning_agent` VARCHAR(255) NULL COMMENT 'task generate planner name',
  `planning_model` VARCHAR(255) NULL COMMENT 'task generate llm model',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sub_task` (`conv_id`, `sub_task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_tool
-- Source Model: GptsToolEntity
CREATE TABLE IF NOT EXISTS `gpts_tool` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `tool_name` VARCHAR(255) NOT NULL COMMENT 'tool name',
  `tool_id` VARCHAR(255) NOT NULL COMMENT 'tool id',
  `type` VARCHAR(255) NOT NULL COMMENT 'tool type, api/local/mcp',
  `config` TEXT NOT NULL COMMENT 'tool detail config',
  `owner` VARCHAR(255) NOT NULL COMMENT 'tool owner',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_tool_name` (`tool_id`),
  KEY `idx_tool_detail_id` (`tool_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_tool_detail
-- Source Model: GptsToolDetailEntity
CREATE TABLE IF NOT EXISTS `gpts_tool_detail` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `tool_id` VARCHAR(255) NOT NULL COMMENT 'tool id',
  `type` VARCHAR(255) NOT NULL COMMENT 'tool type, http/tr/local/mcp',
  `name` VARCHAR(255) NOT NULL COMMENT 'tool name',
  `sub_name` VARCHAR(255) NULL COMMENT 'tool sub name',
  `description` TEXT NULL COMMENT 'tool description',
  `sub_description` TEXT NULL COMMENT 'tool sub description',
  `input_schema` TEXT NULL COMMENT 'tool detail config',
  `category` VARCHAR(255) NULL COMMENT 'tool category',
  `tag` VARCHAR(255) NULL COMMENT 'tool tag',
  `owner` VARCHAR(255) NULL COMMENT 'tool owner',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_tool_detail_id` (`tool_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_tool_messages
-- Source Model: GptsToolMessagesEntity
CREATE TABLE IF NOT EXISTS `gpts_tool_messages` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `tool_id` VARCHAR(255) NOT NULL COMMENT 'tool id',
  `name` VARCHAR(255) NOT NULL COMMENT 'tool name',
  `sub_name` VARCHAR(255) NULL COMMENT 'tool sub name',
  `type` VARCHAR(255) NOT NULL COMMENT 'tool type, api/local/mcp',
  `input` TEXT NULL COMMENT 'tool input',
  `output` TEXT NULL COMMENT 'tool output',
  `success` INT NOT NULL COMMENT 'tool success',
  `error` TEXT NULL COMMENT 'tool error',
  `trace_id` VARCHAR(255) NULL COMMENT 'tool trace id',
  `session_id` VARCHAR(255) NULL COMMENT 'tool session id',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_tool_id` (`tool_id`),
  KEY `idx_tool_name` (`name`),
  KEY `idx_tool_name_sub_name` (`name`, `sub_name`),
  KEY `idx_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_work_log
-- Source Model: GptsWorkLogEntity
CREATE TABLE IF NOT EXISTS `gpts_work_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation',
  `session_id` VARCHAR(255) NOT NULL COMMENT 'The session id within conversation',
  `agent_id` VARCHAR(255) NOT NULL COMMENT 'The agent id that created this log',
  `step_index` INT NOT NULL DEFAULT 0 COMMENT 'The step index in the session',
  `tool` VARCHAR(255) NOT NULL COMMENT 'Tool name',
  `args` TEXT NULL COMMENT 'Tool arguments (JSON)',
  `summary` TEXT NULL COMMENT 'Brief summary of the action',
  `result` LONGTEXT NULL COMMENT 'Result content',
  `full_result_archive` VARCHAR(512) NULL COMMENT 'File key for archived full result',
  `archives` TEXT NULL COMMENT 'List of archive file keys (JSON)',
  `success` INT NOT NULL DEFAULT 1 COMMENT 'Whether the action succeeded',
  `tags` TEXT NULL COMMENT 'Tags (JSON array)',
  `tokens` INT NOT NULL DEFAULT 0 COMMENT 'Estimated token count',
  `status` VARCHAR(32) NOT NULL COMMENT 'Status: active/compressed/archived',
  `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When the action was performed',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_work_log_conv_session` (`conv_id`, `session_id`),
  KEY `idx_work_log_conv_tool` (`conv_id`, `tool`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_app_config
-- Source Model: ServeEntity
CREATE TABLE IF NOT EXISTS `gpts_app_config` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `code` VARCHAR(100) NOT NULL COMMENT '当前配置代码',
  `app_code` VARCHAR(100) NOT NULL COMMENT '应用代码',
  `team_mode` VARCHAR(255) NOT NULL COMMENT '当前版本配置的对话模式',
  `team_context` TEXT NULL COMMENT '应用当前版本的TeamContext信息',
  `resources` LONGTEXT NULL COMMENT '应用当前版本的Resources信息',
  `details` VARCHAR(2000) NULL COMMENT '应用当前版本的小弟details信息',
  `recommend_questions` TEXT NULL COMMENT '当前版本配置设定的推进问题信息',
  `version_info` VARCHAR(1000) NOT NULL COMMENT '版本信息',
  `creator` VARCHAR(255) NULL COMMENT '创建者(域账户)',
  `description` VARCHAR(1000) NULL COMMENT '当前版本配置的备注描述',
  `is_published` SMALLINT NULL DEFAULT 0 COMMENT '当前版本配置的备注描述',
  `gmt_last_edit` DATETIME NULL COMMENT '当前版本配置最后一次内容编辑时间',
  `editor` VARCHAR(255) NULL COMMENT '当前版本配置最后修改者',
  `ext_config` LONGTEXT NULL COMMENT '当前版本配置的扩展配置，各自动态扩展的内容',
  `runtime_config` LONGTEXT NULL COMMENT 'Agent运行时配置，包含DoomLoop检测、Loop执行、WorkLog压缩等',
  `system_prompt_template` TEXT NULL COMMENT '当前版本配置的system prompt模版',
  `user_prompt_template` TEXT NULL COMMENT '当前版本配置的user prompt模版',
  `layout` VARCHAR(255) NULL COMMENT '当前版本配置的布局配置',
  `custom_variables` TEXT NULL COMMENT '当前版本配置自定义参数配置',
  `llm_config` TEXT NULL COMMENT '当前版本配置的模型配置',
  `resource_knowledge` TEXT NULL COMMENT '当前版本配置的知识配置',
  `resource_tool` TEXT NULL COMMENT '当前版本配置的工具配置',
  `resource_agent` TEXT NULL COMMENT '当前版本配置的agent配置',
  `context_config` VARCHAR(2000) NULL COMMENT '上下文工程配置',
  `agent_version` VARCHAR(32) NULL COMMENT 'agent version: v1 or v2',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_version` (`code`),
  KEY `idx_app_config` (`app_code`, `is_published`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: connect_config
-- Source Model: ConnectConfigEntity
CREATE TABLE IF NOT EXISTS `connect_config` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `db_type` VARCHAR(255) NOT NULL COMMENT 'db type',
  `db_name` VARCHAR(255) NOT NULL COMMENT 'db name',
  `db_path` VARCHAR(255) NULL COMMENT 'file db path',
  `db_host` VARCHAR(255) NULL COMMENT 'db connect host(not file db)',
  `db_port` VARCHAR(255) NULL COMMENT 'db connect port(not file db)',
  `db_user` VARCHAR(255) NULL COMMENT 'db user',
  `db_pwd` VARCHAR(255) NULL COMMENT 'db password',
  `comment` TEXT NULL COMMENT 'db comment',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `user_id` VARCHAR(128) NULL COMMENT 'User id',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `ext_config` TEXT NULL COMMENT 'Extended configuration, json format',
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_db` (`db_name`),
  KEY `idx_q_db_type` (`db_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: db_spec
-- Source Model: DbSpecEntity
CREATE TABLE IF NOT EXISTS `db_spec` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `datasource_id` INT NOT NULL COMMENT 'FK to connect_config.id',
  `db_name` VARCHAR(255) NOT NULL COMMENT 'Database name',
  `db_type` VARCHAR(64) NOT NULL COMMENT 'Database type',
  `spec_content` TEXT NOT NULL COMMENT 'JSON: table list index with summaries',
  `table_count` INT NULL COMMENT 'Total number of tables',
  `group_config` TEXT NULL COMMENT 'JSON: table grouping configuration',
  `relations` TEXT NULL COMMENT 'JSON: detected table relationships',
  `status` VARCHAR(32) NOT NULL COMMENT 'Status: ready, generating, failed',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_db_spec_datasource` (`datasource_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: db_learning_subtask
-- Source Model: DbLearningSubtaskEntity
CREATE TABLE IF NOT EXISTS `db_learning_subtask` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `task_id` INT NOT NULL COMMENT 'FK to db_learning_task.id',
  `datasource_id` INT NOT NULL COMMENT 'FK to connect_config.id (denormalized)',
  `table_name` VARCHAR(255) NOT NULL COMMENT 'Table name to learn',
  `status` VARCHAR(32) NOT NULL COMMENT 'Status: pending, claimed, completed, failed, cancelled',
  `worker_id` VARCHAR(128) NULL COMMENT 'hostname:pid:thread that claimed this subtask',
  `attempt_count` INT NOT NULL DEFAULT 0 COMMENT 'Number of claim attempts',
  `max_attempts` INT NOT NULL DEFAULT 3 COMMENT 'Max retry attempts',
  `error_message` TEXT NULL COMMENT 'Error details on failure',
  `claimed_at` DATETIME NULL COMMENT 'When a worker claimed this subtask',
  `completed_at` DATETIME NULL COMMENT 'When the subtask finished',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_subtask_task_table` (`task_id`, `table_name`),
  KEY `idx_subtask_task_status` (`task_id`, `status`),
  KEY `idx_subtask_ds` (`datasource_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: db_learning_task
-- Source Model: DbLearningTaskEntity
CREATE TABLE IF NOT EXISTS `db_learning_task` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `datasource_id` INT NOT NULL COMMENT 'FK to connect_config.id',
  `task_type` VARCHAR(32) NOT NULL COMMENT 'Task type: full_learn, single_table',
  `status` VARCHAR(32) NOT NULL COMMENT 'Status: pending, running, finalizing, completed, failed, cancelled',
  `progress` INT NOT NULL DEFAULT 0 COMMENT 'Progress 0-100',
  `total_tables` INT NULL COMMENT 'Total number of tables to process',
  `processed_tables` INT NOT NULL DEFAULT 0 COMMENT 'Number of tables processed',
  `error_message` TEXT NULL COMMENT 'Error message if task failed',
  `trigger_type` VARCHAR(32) NOT NULL COMMENT 'Trigger type: manual, auto_on_create, scheduled',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_learning_task_ds` (`datasource_id`),
  KEY `idx_learning_task_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: table_spec
-- Source Model: TableSpecEntity
CREATE TABLE IF NOT EXISTS `table_spec` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `datasource_id` INT NOT NULL COMMENT 'FK to connect_config.id',
  `table_name` VARCHAR(255) NOT NULL COMMENT 'Table name',
  `table_comment` TEXT NULL COMMENT 'Table comment/description',
  `row_count` INT NULL COMMENT 'Approximate row count',
  `columns_json` TEXT NOT NULL COMMENT 'JSON: array of column definitions ',
  `indexes_json` TEXT NULL COMMENT 'JSON: array of index definitions (name, columns, unique)',
  `sample_data_json` TEXT NULL COMMENT 'JSON: sample rows from the table',
  `create_ddl` TEXT NULL COMMENT 'CREATE TABLE DDL statement',
  `foreign_keys_json` TEXT NULL COMMENT 'JSON: array of foreign key definitions ',
  `group_name` VARCHAR(128) NULL COMMENT 'Table group name for categorization',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_table_spec_ds_table` (`datasource_id`, `table_name`),
  KEY `idx_table_spec_ds` (`datasource_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: evaluate_manage
-- Source Model: ServeEntity
CREATE TABLE IF NOT EXISTS `evaluate_manage` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `evaluate_code` VARCHAR(256) NULL COMMENT 'evaluate Code',
  `scene_key` VARCHAR(100) NULL COMMENT 'evaluate scene key',
  `scene_value` VARCHAR(256) NULL COMMENT 'evaluate scene value',
  `context` TEXT NULL COMMENT 'evaluate scene run context',
  `evaluate_metrics` VARCHAR(599) NULL COMMENT 'evaluate metrics',
  `datasets_name` VARCHAR(256) NULL COMMENT 'datasets name',
  `datasets` TEXT NULL COMMENT 'datasets',
  `storage_type` VARCHAR(256) NULL COMMENT 'datasets storage type',
  `parallel_num` INT NULL COMMENT 'datasets run parallel num',
  `state` VARCHAR(100) NULL COMMENT 'evaluate state',
  `result` TEXT NULL COMMENT 'evaluate result',
  `log_info` TEXT NULL COMMENT 'evaluate log info',
  `average_score` TEXT NULL COMMENT 'evaluate average score',
  `user_id` VARCHAR(100) NULL COMMENT 'User id',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_evaluate_code` (`evaluate_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_feed_back
-- Source Model: ServeEntity
CREATE TABLE IF NOT EXISTS `chat_feed_back` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `conv_uid` VARCHAR(128) NULL,
  `conv_index` INT NULL,
  `score` INT NULL,
  `ques_type` VARCHAR(32) NULL,
  `question` TEXT NULL,
  `knowledge_space` VARCHAR(128) NULL,
  `messages` TEXT NULL,
  `remark` TEXT NULL COMMENT 'feedback remark',
  `message_id` VARCHAR(255) NULL COMMENT 'Message ID',
  `feedback_type` VARCHAR(31) NULL COMMENT 'Feedback type like or unlike',
  `reason_types` VARCHAR(255) NULL COMMENT 'Feedback reason categories',
  `user_code` VARCHAR(255) NULL COMMENT 'User ID',
  `user_name` VARCHAR(128) NULL,
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Modification time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_conv_uid` (`conv_uid`),
  KEY `idx_gmt_create` (`gmt_create`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: prompt_manage
-- Source Model: ServeEntity
CREATE TABLE IF NOT EXISTS `prompt_manage` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `chat_scene` VARCHAR(100) NULL COMMENT 'Chat scene',
  `sub_chat_scene` VARCHAR(100) NULL COMMENT 'Sub chat scene',
  `prompt_code` VARCHAR(256) NULL COMMENT 'Prompt Code',
  `prompt_type` VARCHAR(100) NULL COMMENT 'Prompt type(eg: common, private)',
  `prompt_name` VARCHAR(256) NULL COMMENT 'Prompt name',
  `content` TEXT NULL COMMENT 'Prompt content',
  `response_schema` TEXT NULL COMMENT 'Prompt response schema',
  `gmt_create` VARCHAR(128) NULL COMMENT 'Prompt model name(we can use different models for different prompt',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_prompt_name_sys_code` (`prompt_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: document_chunk
-- Source Model: DocumentChunkEntity
CREATE TABLE IF NOT EXISTS `document_chunk` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `chunk_id` VARCHAR(100) NULL,
  `document_id` INT NULL,
  `doc_name` VARCHAR(100) NULL,
  `knowledge_uid` VARCHAR(100) NULL,
  `word_count` INT NULL,
  `doc_type` VARCHAR(100) NULL,
  `doc_id` VARCHAR(100) NULL,
  `content` TEXT NULL,
  `questions` TEXT NULL,
  `vector_id` VARCHAR(100) NULL,
  `full_text_id` VARCHAR(100) NULL,
  `meta_data` TEXT NULL,
  `tags` TEXT NULL,
  `chunk_type` VARCHAR(100) NULL,
  `image_url` VARCHAR(2048) NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_document
-- Source Model: KnowledgeDocumentEntity
CREATE TABLE IF NOT EXISTS `knowledge_document` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `doc_id` VARCHAR(100) NULL,
  `doc_name` VARCHAR(100) NULL,
  `doc_type` VARCHAR(100) NULL,
  `doc_token` VARCHAR(100) NULL,
  `knowledge_id` VARCHAR(100) NULL,
  `space` VARCHAR(100) NULL,
  `chunk_size` INT NULL,
  `status` VARCHAR(100) NULL,
  `content` TEXT NULL,
  `chunk_params` TEXT NULL,
  `doc_params` TEXT NULL,
  `meta_data` TEXT NULL,
  `result` TEXT NULL,
  `vector_ids` TEXT NULL,
  `summary` TEXT NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  `questions` TEXT NULL,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: graph_node
-- Source Model: GraphNodeEntity
CREATE TABLE IF NOT EXISTS `graph_node` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `project_id` INT NULL,
  `node_id` VARCHAR(100) NULL,
  `name` VARCHAR(100) NULL,
  `name_zh` VARCHAR(100) NULL,
  `description` TEXT NULL,
  `scope` VARCHAR(100) NULL,
  `version` VARCHAR(100) NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_refresh_record
-- Source Model: KnowledgeRefreshRecordEntity
CREATE TABLE IF NOT EXISTS `knowledge_refresh_record` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `refresh_id` VARCHAR(100) NULL,
  `knowledge_id` VARCHAR(100) NULL,
  `refresh_time` VARCHAR(100) NULL,
  `host` VARCHAR(100) NULL,
  `status` VARCHAR(100) NULL,
  `operator` VARCHAR(100) NULL,
  `error_msg` VARCHAR(100) NULL,
  `context` TEXT NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_space_graph_relation
-- Source Model: KnowledgeSpaceGraphRelationEntity
CREATE TABLE IF NOT EXISTS `knowledge_space_graph_relation` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `knowledge_id` VARCHAR(100) NULL,
  `storage_type` VARCHAR(100) NULL,
  `project_id` INT NULL,
  `project_name` VARCHAR(100) NULL,
  `user_token` VARCHAR(100) NULL,
  `user_login_name` VARCHAR(100) NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_task
-- Source Model: KnowledgeTaskEntity
CREATE TABLE IF NOT EXISTS `knowledge_task` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` VARCHAR(100) NULL,
  `knowledge_id` VARCHAR(100) NULL,
  `doc_id` VARCHAR(100) NULL,
  `doc_action` VARCHAR(100) NULL,
  `doc_type` VARCHAR(100) NULL,
  `doc_content` VARCHAR(100) NULL,
  `yuque_token` VARCHAR(100) NULL,
  `group_login` VARCHAR(100) NULL,
  `book_slug` VARCHAR(100) NULL,
  `yuque_doc_id` VARCHAR(100) NULL,
  `chunk_parameters` VARCHAR(100) NULL,
  `status` VARCHAR(100) NULL,
  `owner` VARCHAR(100) NULL,
  `batch_id` VARCHAR(100) NULL,
  `retry_times` INT NULL,
  `error_msg` VARCHAR(100) NULL,
  `start_time` VARCHAR(100) NULL,
  `end_time` VARCHAR(100) NULL,
  `host` VARCHAR(100) NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_space
-- Source Model: KnowledgeSpaceEntity
CREATE TABLE IF NOT EXISTS `knowledge_space` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `knowledge_id` VARCHAR(100) NULL,
  `name` VARCHAR(100) NULL,
  `storage_type` VARCHAR(100) NULL,
  `domain_type` VARCHAR(100) NULL,
  `tags` VARCHAR(500) NULL,
  `category` VARCHAR(100) NULL,
  `knowledge_type` VARCHAR(100) NULL,
  `description` VARCHAR(100) NULL,
  `owner` VARCHAR(100) NULL,
  `sys_code` VARCHAR(128) NULL,
  `context` TEXT NULL,
  `refresh` VARCHAR(100) NULL,
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rag_flow_span
-- Source Model: RagFlowSpan
CREATE TABLE IF NOT EXISTS `rag_flow_span` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `span_id` VARCHAR(100) NULL,
  `span_type` VARCHAR(100) NULL,
  `trace_id` VARCHAR(100) NULL,
  `app_code` VARCHAR(100) NULL,
  `conv_id` VARCHAR(100) NULL,
  `message_id` VARCHAR(100) NULL,
  `input` TEXT NULL,
  `output` TEXT NULL,
  `start_time` VARCHAR(500) NULL,
  `end_time` VARCHAR(500) NULL,
  `node_name` VARCHAR(500) NULL,
  `node_type` VARCHAR(500) NULL,
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: settings
-- Source Model: SettingsEntity
CREATE TABLE IF NOT EXISTS `settings` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `setting_key` VARCHAR(100) NULL,
  `value` VARCHAR(1000) NULL,
  `description` VARCHAR(100) NULL,
  `operator` VARCHAR(100) NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_yuque
-- Source Model: KnowledgeYuqueEntity
CREATE TABLE IF NOT EXISTS `knowledge_yuque` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `yuque_id` VARCHAR(100) NULL,
  `doc_id` VARCHAR(100) NULL,
  `knowledge_id` VARCHAR(100) NULL,
  `title` VARCHAR(100) NULL,
  `token` VARCHAR(100) NULL,
  `token_type` VARCHAR(100) NULL,
  `group_login` VARCHAR(100) NULL,
  `group_login_name` VARCHAR(100) NULL,
  `book_slug` VARCHAR(100) NULL,
  `book_slug_name` VARCHAR(100) NULL,
  `doc_slug` VARCHAR(100) NULL,
  `doc_uuid` VARCHAR(100) NULL,
  `yuque_doc_id` VARCHAR(100) NULL,
  `backup_doc_uuid` VARCHAR(100) NULL,
  `word_cnt` INT NULL,
  `latest_version_id` VARCHAR(100) NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  `description` TEXT NULL,
  `created_at` VARCHAR(100) NULL,
  `updated_at` VARCHAR(100) NULL,
  `cover` VARCHAR(100) NULL,
  `creator_login_name` VARCHAR(100) NULL,
  `avatar_url` VARCHAR(100) NULL,
  `likes_count` INT NULL,
  `read_count` INT NULL,
  `comments_count` INT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: scene_strategy
-- Source Model: SceneStrategyEntity
CREATE TABLE IF NOT EXISTS `scene_strategy` (
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: app_scene_binding
-- Source Model: AppSceneBindingEntity
CREATE TABLE IF NOT EXISTS `app_scene_binding` (
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: skill_sync_task
-- Source Model: SkillSyncTaskEntity
CREATE TABLE IF NOT EXISTS `skill_sync_task` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `task_id` VARCHAR(100) NOT NULL COMMENT 'unique task identifier',
  `repo_url` VARCHAR(500) NOT NULL COMMENT 'git repository url',
  `branch` VARCHAR(100) NOT NULL COMMENT 'git branch',
  `force_update` TINYINT(1) NULL DEFAULT 0 COMMENT 'force update existing skills',
  `status` VARCHAR(50) NOT NULL COMMENT 'task status: pending, running, completed, failed',
  `progress` INT NULL DEFAULT 0 COMMENT 'progress percentage (0-100)',
  `current_step` VARCHAR(200) NULL COMMENT 'current step description',
  `total_steps` INT NULL DEFAULT 0 COMMENT 'total number of steps',
  `steps_completed` INT NULL DEFAULT 0 COMMENT 'number of steps completed',
  `synced_skills_count` INT NULL DEFAULT 0 COMMENT 'number of skills synced',
  `skill_codes` TEXT NULL COMMENT 'JSON list of synced skill codes',
  `error_msg` TEXT NULL COMMENT 'error message if failed',
  `error_details` TEXT NULL COMMENT 'detailed error information',
  `start_time` DATETIME NULL COMMENT 'task start time',
  `end_time` DATETIME NULL COMMENT 'task end time',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: sql_audit_log
-- Source Model: SqlAuditLogEntity
CREATE TABLE IF NOT EXISTS `sql_audit_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto-increment ID',
  `user_id` VARCHAR(255) NULL COMMENT 'User identifier',
  `session_id` VARCHAR(255) NULL COMMENT 'Session identifier',
  `datasource_id` INT NULL COMMENT 'Datasource ID',
  `db_name` VARCHAR(255) NULL COMMENT 'Database name',
  `agent_name` VARCHAR(255) NULL COMMENT 'Agent name',
  `sql_text` TEXT NULL COMMENT 'SQL statement (truncated)',
  `sql_type` VARCHAR(32) NULL COMMENT 'SQL type (SELECT/INSERT/...)',
  `guard_mode` VARCHAR(32) NULL COMMENT 'Guard mode (readonly/readwrite/admin)',
  `check_result` VARCHAR(16) NULL COMMENT 'Check result (allowed/blocked/warning)',
  `risk_level` VARCHAR(16) NULL COMMENT 'Risk level',
  `risk_score` INT NULL COMMENT 'Risk score (0-100)',
  `blocked_rules` TEXT NULL COMMENT 'Blocked rule names (comma-separated)',
  `execution_time_ms` FLOAT NULL COMMENT 'SQL execution time in milliseconds',
  `row_count` INT NULL COMMENT 'Result row count',
  `error_message` TEXT NULL COMMENT 'Error message if failed',
  `duration_ms` FLOAT NULL COMMENT 'Guard check duration in ms',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When the audit log was created',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_sql_audit_user` (`user_id`),
  KEY `idx_sql_audit_ds` (`datasource_id`),
  KEY `idx_sql_audit_time` (`created_at`),
  KEY `idx_sql_audit_session` (`session_id`),
  KEY `idx_sql_audit_result` (`check_result`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: sensitive_column_config
-- Source Model: SensitiveColumnEntity
CREATE TABLE IF NOT EXISTS `sensitive_column_config` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto-increment ID',
  `datasource_id` INT NOT NULL COMMENT 'Datasource ID',
  `table_name` VARCHAR(255) NOT NULL COMMENT 'Table name',
  `column_name` VARCHAR(255) NOT NULL COMMENT 'Column name',
  `sensitive_type` VARCHAR(32) NOT NULL COMMENT 'Sensitive type: phone/email/id_card/bank_card/address/name/password/token/custom',
  `masking_mode` VARCHAR(16) NOT NULL COMMENT 'Masking mode: mask/token/none',
  `confidence` FLOAT NULL COMMENT 'Auto-detection confidence (0-1), null if manually configured',
  `source` VARCHAR(16) NOT NULL COMMENT 'Config source: auto (detected) / manual (user-configured)',
  `enabled` INT NOT NULL DEFAULT 1 COMMENT 'Whether masking is active for this column',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sensitive_col` (`datasource_id`, `table_name`, `column_name`),
  KEY `idx_sensitive_col_ds` (`datasource_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- End of DDL Script
-- ============================================================