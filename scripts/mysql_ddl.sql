-- ============================================================
-- MySQL DDL Script for Derisk
-- Generated from SQLAlchemy ORM Models
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- Core Tables
-- ============================================================

-- Table: derisk_cluster_registry_instance
CREATE TABLE IF NOT EXISTS `derisk_cluster_registry_instance` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `model_name` VARCHAR(128) NOT NULL COMMENT 'Model name',
  `host` VARCHAR(128) NOT NULL COMMENT 'Host of the model',
  `port` INT NOT NULL COMMENT 'Port of the model',
  `weight` FLOAT NULL DEFAULT 1.0 COMMENT 'Weight of the model',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_model_instance` (`model_name`, `host`, `port`, `sys_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_history
CREATE TABLE IF NOT EXISTS `chat_history` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
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
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conv_uid` (`conv_uid`),
  KEY `idx_q_user` (`user_name`),
  KEY `idx_q_mode` (`chat_mode`),
  KEY `idx_q_conv` (`summary`(255)),
  KEY `idx_chat_his_app_code` (`app_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_history_message
CREATE TABLE IF NOT EXISTS `chat_history_message` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_uid` VARCHAR(255) NOT NULL COMMENT 'Conversation record unique id',
  `index` INT NOT NULL COMMENT 'Message index',
  `round_index` INT NOT NULL COMMENT 'Message round index',
  `message_detail` LONGTEXT NULL COMMENT 'Message details, json format',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conversation_message` (`conv_uid`, `index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- GPTS Tables
-- ============================================================

-- Table: gpts_app
CREATE TABLE IF NOT EXISTS `gpts_app` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `app_code` VARCHAR(255) NOT NULL COMMENT 'Current AI assistant code',
  `app_name` VARCHAR(255) NOT NULL COMMENT 'Current AI assistant name',
  `app_hub_code` VARCHAR(255) NULL COMMENT 'app hub code',
  `icon` VARCHAR(1024) NULL COMMENT 'app icon, url',
  `app_describe` VARCHAR(2255) NOT NULL COMMENT 'Current AI assistant describe',
  `language` VARCHAR(100) NOT NULL COMMENT 'gpts language',
  `team_mode` VARCHAR(255) NOT NULL COMMENT 'Team work mode',
  `team_context` TEXT NULL COMMENT 'The execution logic and team member content',
  `config_code` VARCHAR(255) NULL COMMENT 'app config code',
  `config_version` VARCHAR(255) NULL COMMENT 'app config version',
  `user_code` VARCHAR(255) NULL COMMENT 'user code',
  `sys_code` VARCHAR(255) NULL COMMENT 'system app code',
  `published` VARCHAR(64) NULL COMMENT 'published',
  `param_need` TEXT NULL COMMENT 'Parameters required for application',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `admins` TEXT NULL COMMENT 'administrators',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gpts_app` (`app_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_app_detail
CREATE TABLE IF NOT EXISTS `gpts_app_detail` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `app_code` VARCHAR(255) NOT NULL COMMENT 'Current AI assistant code',
  `app_name` VARCHAR(255) NOT NULL COMMENT 'Current AI assistant name',
  `type` VARCHAR(255) NOT NULL COMMENT 'bind detail agent type',
  `agent_name` VARCHAR(255) NOT NULL COMMENT 'Agent name',
  `agent_role` VARCHAR(255) NOT NULL COMMENT 'Agent role',
  `agent_describe` TEXT NULL COMMENT 'Agent describe',
  `node_id` VARCHAR(255) NOT NULL COMMENT 'Current AI assistant Agent Node id',
  `resources` TEXT NULL COMMENT 'Agent bind resource',
  `prompt_template` TEXT NULL COMMENT 'Agent bind template',
  `llm_strategy` VARCHAR(25) NULL COMMENT 'Agent use llm strategy',
  `llm_strategy_value` TEXT NULL COMMENT 'Agent use llm strategy value',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gpts_app_agent_node` (`app_name`, `agent_name`, `node_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_app_config
CREATE TABLE IF NOT EXISTS `gpts_app_config` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `code` VARCHAR(100) NOT NULL COMMENT '当前配置代码',
  `app_code` VARCHAR(100) NOT NULL COMMENT '应用代码',
  `team_mode` VARCHAR(255) NOT NULL COMMENT '当前版本配置的对话模式',
  `team_context` TEXT NULL COMMENT '应用当前版本的TeamContext信息',
  `resources` TEXT NULL COMMENT '应用当前版本的Resources信息',
  `details` VARCHAR(2000) NULL COMMENT '应用当前版本的小弟details信息',
  `recommend_questions` TEXT NULL COMMENT '当前版本配置设定的推进问题信息',
  `version_info` VARCHAR(1000) NOT NULL COMMENT '版本信息',
  `creator` VARCHAR(255) NULL COMMENT '创建者(域账户)',
  `description` VARCHAR(1000) NULL COMMENT '当前版本配置的备注描述',
  `is_published` SMALLINT NULL DEFAULT 0 COMMENT '当前版本配置的备注描述',
  `gmt_last_edit` DATETIME NULL COMMENT '当前版本配置最后一次内容编辑时间',
  `editor` VARCHAR(255) NULL COMMENT '当前版本配置最后修改者',
  `ext_config` TEXT NULL COMMENT '当前版本配置的扩展配置',
  `system_prompt_template` TEXT NULL COMMENT '当前版本配置的system prompt模版',
  `user_prompt_template` TEXT NULL COMMENT '当前版本配置的user prompt模版',
  `layout` VARCHAR(255) NULL COMMENT '当前版本配置的布局配置',
  `custom_variables` VARCHAR(2000) NULL COMMENT '当前版本配置自定义参数配置',
  `llm_config` VARCHAR(1000) NULL COMMENT '当前版本配置的模型配置',
  `resource_knowledge` VARCHAR(2000) NULL COMMENT '当前版本配置的知识配置',
  `resource_tool` VARCHAR(2000) NULL COMMENT '当前版本配置的工具配置',
  `resource_agent` VARCHAR(2000) NULL COMMENT '当前版本配置的agent配置',
  `context_config` VARCHAR(2000) NULL COMMENT '上下文工程配置',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_version` (`code`),
  KEY `idx_app_config` (`app_code`, `is_published`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: user_recent_apps
CREATE TABLE IF NOT EXISTS `user_recent_apps` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `app_code` VARCHAR(255) NOT NULL COMMENT 'Current AI assistant code',
  `user_code` VARCHAR(255) NULL COMMENT 'user code',
  `sys_code` VARCHAR(255) NULL COMMENT 'system app code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  `last_accessed` DATETIME NULL COMMENT 'last access time',
  PRIMARY KEY (`id`),
  KEY `idx_user_r_app_code` (`app_code`),
  KEY `idx_user_code` (`user_code`),
  KEY `idx_last_accessed` (`last_accessed`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_conversations
CREATE TABLE IF NOT EXISTS `gpts_conversations` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `user_goal` TEXT NOT NULL COMMENT 'User''s goals content',
  `gpts_name` VARCHAR(255) NOT NULL COMMENT 'The gpts name',
  `team_mode` VARCHAR(255) NOT NULL COMMENT 'The conversation team mode',
  `state` VARCHAR(255) NULL COMMENT 'The gpts state',
  `max_auto_reply_round` INT NOT NULL COMMENT 'max auto reply round',
  `auto_reply_count` INT NOT NULL COMMENT 'auto reply count',
  `user_code` VARCHAR(255) NULL COMMENT 'user code',
  `sys_code` VARCHAR(255) NULL COMMENT 'system app',
  `vis_render` VARCHAR(255) NULL COMMENT 'vis mode of chat conversation',
  `extra` TEXT NULL COMMENT 'the extra info of the conversation',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gpts_conversations` (`conv_id`),
  KEY `idx_gpts_name` (`gpts_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_messages
CREATE TABLE IF NOT EXISTS `gpts_messages` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `message_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the messages',
  `sender` VARCHAR(255) NOT NULL COMMENT 'Who(role) speaking in the current conversation turn',
  `sender_name` VARCHAR(255) NOT NULL COMMENT 'Who(name) speaking in the current conversation turn',
  `receiver` VARCHAR(255) NOT NULL COMMENT 'Who(role) receive message',
  `receiver_name` VARCHAR(255) NOT NULL COMMENT 'Who(name) receive message',
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
  `user_prompt` LONGTEXT NULL COMMENT 'this message user prompt',
  `show_message` TINYINT(1) NULL COMMENT 'Whether the current message needs to be displayed',
  `goal_id` VARCHAR(255) NULL COMMENT 'The target id to the current message',
  `current_goal` TEXT NULL COMMENT 'The target corresponding to the current message',
  `context` TEXT NULL COMMENT 'Current conversation context',
  `review_info` TEXT NULL COMMENT 'Current conversation review info',
  `action_report` LONGTEXT NULL COMMENT 'Current conversation action report',
  `resource_info` TEXT NULL COMMENT 'Current conversation resource info',
  `role` VARCHAR(255) NULL COMMENT 'The role of the current message content',
  `avatar` VARCHAR(255) NULL COMMENT 'The avatar of the agent who send current message',
  `metrics` VARCHAR(1000) NULL COMMENT 'The performance metrics of agent messages',
  `tool_calls` LONGTEXT NULL COMMENT 'The tool_calls of agent messages',
  `observation` LONGTEXT NULL COMMENT 'The message observation',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  PRIMARY KEY (`id`),
  KEY `idx_q_messages` (`conv_id`, `rounds`, `sender`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_messages_system
CREATE TABLE IF NOT EXISTS `gpts_messages_system` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
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
  `content` LONGTEXT NULL COMMENT '消息内容',
  `content_extra` VARCHAR(2000) NULL COMMENT '消息扩展内容',
  `retry_time` SMALLINT NULL DEFAULT 0 COMMENT '当前阶段重试次数',
  `final_status` VARCHAR(20) NULL COMMENT '当前阶段最终状态',
  PRIMARY KEY (`id`),
  KEY `idx_message_phase` (`conv_id`, `phase`),
  KEY `idx_message_type` (`conv_id`, `type`, `phase`),
  KEY `idx_agent_message` (`conv_id`, `agent_message_id`),
  KEY `idx_message` (`message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_plans
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
  `result` LONGTEXT NULL COMMENT 'subtask result',
  `task_round_title` VARCHAR(255) NULL COMMENT 'task round title',
  `task_round_description` VARCHAR(500) NULL COMMENT 'task round description',
  `planning_agent` VARCHAR(255) NULL COMMENT 'task generate planner name',
  `planning_model` VARCHAR(255) NULL COMMENT 'task generate llm model',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sub_task` (`conv_id`, `sub_task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_tool
CREATE TABLE IF NOT EXISTS `gpts_tool` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `tool_name` VARCHAR(255) NOT NULL COMMENT 'tool name',
  `tool_id` VARCHAR(255) NOT NULL COMMENT 'tool id',
  `type` VARCHAR(255) NOT NULL COMMENT 'tool type, api/local/mcp',
  `config` TEXT NOT NULL COMMENT 'tool detail config',
  `owner` VARCHAR(255) NOT NULL COMMENT 'tool owner',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'last update time',
  PRIMARY KEY (`id`),
  KEY `idx_tool_id` (`tool_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_tool_detail
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
  PRIMARY KEY (`id`),
  KEY `idx_tool_id` (`tool_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_tool_messages
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
  PRIMARY KEY (`id`),
  KEY `idx_tool_id` (`tool_id`),
  KEY `idx_tool_name` (`name`),
  KEY `idx_tool_name_sub_name` (`name`, `sub_name`),
  KEY `idx_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Recommend Question Table
-- ============================================================

-- Table: recommend_question
CREATE TABLE IF NOT EXISTS `recommend_question` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `app_code` VARCHAR(255) NOT NULL COMMENT 'App code',
  `question` TEXT NOT NULL COMMENT 'Question content',
  `user_code` VARCHAR(255) NULL COMMENT 'User code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Update time',
  `params` TEXT NULL COMMENT 'Question params',
  `valid` TINYINT(1) NULL DEFAULT 1 COMMENT 'Valid status',
  `is_hot_question` VARCHAR(10) NULL DEFAULT 'false' COMMENT 'Is hot question',
  PRIMARY KEY (`id`),
  KEY `idx_rec_q_app_code` (`app_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Serve Config Tables
-- ============================================================

-- Table: derisk_serve_config
CREATE TABLE IF NOT EXISTS `derisk_serve_config` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `name` VARCHAR(255) NOT NULL COMMENT 'config key',
  `value` VARCHAR(4096) NULL COMMENT 'config value',
  `type` VARCHAR(255) NULL DEFAULT 'string' COMMENT 'config type[string, json, int, float]',
  `valid_time` INT NULL COMMENT '当前配置项的有效时间(单位秒)',
  `operator` VARCHAR(255) NULL COMMENT 'config operator',
  `creator` VARCHAR(255) NULL COMMENT 'config creator',
  `version` VARCHAR(255) NULL COMMENT 'config version serial',
  `category` VARCHAR(255) NULL COMMENT '配置项类别',
  `upload_cls` VARCHAR(255) NULL COMMENT '需要自动更新值的配置项的更新类实现',
  `upload_param` VARCHAR(1000) NULL COMMENT '需要自动更新值的配置项的更新参数',
  `upload_instance` VARCHAR(255) NULL COMMENT '自动更新值的作业节点实例',
  `upload_stamp` INT NULL COMMENT '自动更新值的时间戳',
  `upload_retry` INT NULL DEFAULT 0 COMMENT '自动更新值的重试次数',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config` (`name`),
  KEY `idx_creator` (`creator`),
  KEY `idx_upload_cls` (`upload_cls`),
  KEY `idx_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_channel_config
CREATE TABLE IF NOT EXISTS `derisk_serve_channel_config` (
  `id` VARCHAR(64) NOT NULL COMMENT 'Channel unique identifier',
  `name` VARCHAR(255) NOT NULL COMMENT 'Channel display name',
  `channel_type` VARCHAR(32) NOT NULL COMMENT 'Channel type (dingtalk/feishu)',
  `enabled` INT NULL DEFAULT 1 COMMENT 'Whether channel is enabled (1=yes, 0=no)',
  `config` JSON NOT NULL COMMENT 'Platform-specific configuration',
  `status` VARCHAR(32) NULL DEFAULT 'disconnected' COMMENT 'Channel status',
  `last_connected` DATETIME NULL COMMENT 'Last successful connection time',
  `last_error` TEXT NULL COMMENT 'Last error message',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_cron_job
CREATE TABLE IF NOT EXISTS `derisk_serve_cron_job` (
  `id` VARCHAR(64) NOT NULL COMMENT 'Job unique identifier',
  `name` VARCHAR(255) NOT NULL COMMENT 'Job name',
  `description` TEXT NULL COMMENT 'Job description',
  `enabled` INT NULL DEFAULT 1 COMMENT 'Whether job is enabled (1=yes, 0=no)',
  `delete_after_run` INT NULL DEFAULT 0 COMMENT 'Delete after run (1=yes, 0=no)',
  `schedule_kind` VARCHAR(32) NOT NULL COMMENT 'Schedule kind (at/every/cron)',
  `schedule_at` VARCHAR(64) NULL COMMENT 'ISO datetime for at schedule',
  `schedule_every_ms` INT NULL COMMENT 'Interval in ms for every schedule',
  `schedule_anchor_ms` INT NULL COMMENT 'Anchor time for every schedule',
  `schedule_expr` VARCHAR(128) NULL COMMENT 'Cron expression for cron schedule',
  `schedule_tz` VARCHAR(64) NULL COMMENT 'Timezone',
  `payload_kind` VARCHAR(32) NOT NULL COMMENT 'Payload kind (agentTurn/toolCall/systemEvent)',
  `payload_data` JSON NULL COMMENT 'Payload data as JSON',
  `session_mode` VARCHAR(16) NULL DEFAULT 'isolated' COMMENT 'Session mode (isolated/shared)',
  `conv_session_id` VARCHAR(64) NULL COMMENT 'Conversation session ID for shared sessions',
  `next_run_at_ms` INT NULL COMMENT 'Next run time in ms',
  `running_at_ms` INT NULL COMMENT 'Current run start time in ms',
  `last_run_at_ms` INT NULL COMMENT 'Last run time in ms',
  `last_status` VARCHAR(32) NULL COMMENT 'Last run status (ok/error/skipped)',
  `last_error` TEXT NULL COMMENT 'Last error message',
  `last_duration_ms` INT NULL COMMENT 'Last run duration in ms',
  `consecutive_errors` INT NULL DEFAULT 0 COMMENT 'Consecutive error count',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: server_app_skill
CREATE TABLE IF NOT EXISTS `server_app_skill` (
  `skill_code` VARCHAR(255) NOT NULL COMMENT 'skill code',
  `name` VARCHAR(255) NOT NULL COMMENT 'skill name',
  `description` TEXT NOT NULL COMMENT 'skill description',
  `type` VARCHAR(255) NOT NULL COMMENT 'skill type',
  `author` VARCHAR(255) NULL COMMENT 'skill author',
  `email` VARCHAR(255) NULL COMMENT 'skill author email',
  `version` VARCHAR(255) NULL COMMENT 'skill version',
  `path` TEXT NULL COMMENT 'skill path',
  `content` TEXT NULL COMMENT 'skill content (markdown)',
  `icon` TEXT NULL COMMENT 'skill icon',
  `category` TEXT NULL COMMENT 'skill category',
  `installed` INT NULL COMMENT 'skill already installed count',
  `available` TINYINT(1) NULL COMMENT 'skill already available',
  `repo_url` TEXT NULL COMMENT 'git repository url',
  `branch` VARCHAR(255) NULL COMMENT 'git branch',
  `commit_id` VARCHAR(255) NULL COMMENT 'git commit id',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`skill_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_mcp
CREATE TABLE IF NOT EXISTS `derisk_serve_mcp` (
  `mcp_code` VARCHAR(255) NOT NULL COMMENT 'mcp code',
  `name` VARCHAR(255) NOT NULL COMMENT 'mcp name',
  `description` TEXT NOT NULL COMMENT 'mcp description',
  `type` VARCHAR(255) NOT NULL COMMENT 'mcp type',
  `author` VARCHAR(255) NULL COMMENT 'mcp author',
  `email` VARCHAR(255) NULL COMMENT 'mcp author email',
  `version` VARCHAR(255) NULL COMMENT 'mcp version',
  `stdio_cmd` TEXT NULL COMMENT 'mcp stdio cmd',
  `sse_url` TEXT NULL COMMENT 'mcp sse connect url',
  `sse_headers` LONGTEXT NULL COMMENT 'mcp sse connect headers',
  `token` LONGTEXT NULL COMMENT 'mcp sse connect token',
  `icon` TEXT NULL COMMENT 'mcp icon',
  `category` TEXT NULL COMMENT 'mcp category',
  `installed` INT NULL COMMENT 'mcp already installed count',
  `available` TINYINT(1) NULL COMMENT 'mcp already available',
  `server_ips` TEXT NULL COMMENT 'mcp server run machine ips',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`mcp_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_model
CREATE TABLE IF NOT EXISTS `derisk_serve_model` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `host` VARCHAR(255) NOT NULL COMMENT 'The model worker host',
  `port` INT NOT NULL COMMENT 'The model worker port',
  `model` VARCHAR(255) NOT NULL COMMENT 'The model name',
  `provider` VARCHAR(255) NOT NULL COMMENT 'The model provider',
  `worker_type` VARCHAR(255) NOT NULL COMMENT 'The worker type',
  `params` TEXT NOT NULL COMMENT 'The model parameters, JSON format',
  `enabled` INT NULL DEFAULT 1 COMMENT 'Whether the model is enabled',
  `worker_name` VARCHAR(255) NULL COMMENT 'The worker name',
  `description` TEXT NULL COMMENT 'The model description',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_model_provider_type` (`model`, `provider`, `worker_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_file
CREATE TABLE IF NOT EXISTS `derisk_serve_file` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `bucket` VARCHAR(255) NOT NULL COMMENT 'Bucket name',
  `file_id` VARCHAR(255) NOT NULL COMMENT 'File id',
  `file_name` VARCHAR(256) NOT NULL COMMENT 'File name',
  `file_size` INT NULL COMMENT 'File size',
  `storage_type` VARCHAR(32) NOT NULL COMMENT 'Storage type',
  `storage_path` VARCHAR(512) NOT NULL COMMENT 'Storage path',
  `uri` VARCHAR(512) NOT NULL COMMENT 'File URI',
  `custom_metadata` TEXT NULL COMMENT 'Custom metadata, JSON format',
  `file_hash` VARCHAR(128) NULL COMMENT 'File hash',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_bucket_file_id` (`bucket`, `file_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_flow
CREATE TABLE IF NOT EXISTS `derisk_serve_flow` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `uid` VARCHAR(128) NOT NULL COMMENT 'Unique id',
  `dag_id` VARCHAR(128) NULL COMMENT 'DAG id',
  `label_info` VARCHAR(128) NULL COMMENT 'Flow label',
  `name` VARCHAR(128) NULL COMMENT 'Flow name',
  `flow_category` VARCHAR(64) NULL COMMENT 'Flow category',
  `flow_data` TEXT NULL COMMENT 'Flow data, JSON format',
  `description` VARCHAR(512) NULL COMMENT 'Flow description',
  `state` VARCHAR(32) NULL COMMENT 'Flow state',
  `error_message` VARCHAR(512) NULL COMMENT 'Error message',
  `source` VARCHAR(64) NULL COMMENT 'Flow source',
  `source_url` VARCHAR(512) NULL COMMENT 'Flow source url',
  `version` VARCHAR(32) NULL COMMENT 'Flow version',
  `define_type` VARCHAR(32) NULL DEFAULT 'json' COMMENT 'Flow define type(json or python)',
  `editable` INT NULL COMMENT 'Editable, 0: editable, 1: not editable',
  `variables` TEXT NULL COMMENT 'Flow variables, JSON format',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_uid` (`uid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_variables
CREATE TABLE IF NOT EXISTS `derisk_serve_variables` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `key_info` VARCHAR(128) NOT NULL COMMENT 'Variable key',
  `name` VARCHAR(128) NULL COMMENT 'Variable name',
  `label_info` VARCHAR(128) NULL COMMENT 'Variable label',
  `value` TEXT NULL COMMENT 'Variable value, JSON format',
  `value_type` VARCHAR(32) NULL COMMENT 'Variable value type(string, int, float, bool)',
  `category` VARCHAR(32) NULL DEFAULT 'common' COMMENT 'Variable categories(common or secret)',
  `encryption_method` VARCHAR(32) NULL COMMENT 'Variable encryption method(fernet, simple, rsa, aes)',
  `salt` VARCHAR(128) NULL COMMENT 'Variable salt',
  `scope` VARCHAR(32) NULL DEFAULT 'global' COMMENT 'Variable scope(global,flow,app,agent,datasource)',
  `scope_key` VARCHAR(256) NULL COMMENT 'Variable scope key',
  `enabled` INT NULL DEFAULT 1 COMMENT 'Variable enabled, 0: disabled, 1: enabled',
  `description` TEXT NULL COMMENT 'Variable description',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  KEY `idx_key_info` (`key_info`),
  KEY `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- RAG Tables
-- ============================================================

-- Table: knowledge_space
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_document
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: document_chunk
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_task
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_yuque
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

-- Table: settings
CREATE TABLE IF NOT EXISTS `settings` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `setting_key` VARCHAR(100) NULL,
  `value` VARCHAR(1000) NULL,
  `description` VARCHAR(100) NULL,
  `operator` VARCHAR(100) NULL,
  `gmt_create` DATETIME NULL,
  `gmt_modified` DATETIME NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_refresh_record
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: knowledge_space_graph_relation
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: graph_node
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rag_flow_span
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Other Tables
-- ============================================================

-- Table: connect_config
CREATE TABLE IF NOT EXISTS `connect_config` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
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
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `ext_config` TEXT NULL COMMENT 'Extended configuration, json format',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_db` (`db_name`),
  KEY `idx_q_db_type` (`db_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: prompt_manage
CREATE TABLE IF NOT EXISTS `prompt_manage` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `chat_scene` VARCHAR(100) NULL COMMENT 'Chat scene',
  `sub_chat_scene` VARCHAR(100) NULL COMMENT 'Sub chat scene',
  `prompt_code` VARCHAR(256) NULL COMMENT 'Prompt Code',
  `prompt_type` VARCHAR(100) NULL COMMENT 'Prompt type(eg: common, private)',
  `prompt_name` VARCHAR(256) NULL COMMENT 'Prompt name',
  `content` TEXT NULL COMMENT 'Prompt content',
  `input_variables` VARCHAR(1024) NULL COMMENT 'Prompt input variables(split by comma)',
  `response_schema` TEXT NULL COMMENT 'Prompt response schema',
  `model` VARCHAR(128) NULL COMMENT 'Prompt model name',
  `prompt_language` VARCHAR(32) NULL COMMENT 'Prompt language(eg:en, zh-cn)',
  `prompt_format` VARCHAR(32) NULL DEFAULT 'f-string' COMMENT 'Prompt format(eg: f-string, jinja2)',
  `prompt_desc` VARCHAR(512) NULL COMMENT 'Prompt description',
  `user_code` VARCHAR(128) NULL COMMENT 'User code',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_prompt_name_sys_code` (`prompt_name`, `sys_code`, `prompt_language`, `model`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_feed_back
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
  PRIMARY KEY (`id`),
  KEY `idx_conv_uid` (`conv_uid`),
  KEY `idx_gmt_create` (`gmt_create`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: evaluate_manage
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
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_evaluate_code` (`evaluate_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: skill_sync_task
CREATE TABLE IF NOT EXISTS `skill_sync_task` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` VARCHAR(100) NOT NULL COMMENT 'unique task identifier',
  `repo_url` VARCHAR(500) NOT NULL COMMENT 'git repository url',
  `branch` VARCHAR(100) NOT NULL COMMENT 'git branch',
  `force_update` TINYINT(1) NULL DEFAULT 0 COMMENT 'force update existing skills',
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
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- End of DDL Script
-- ============================================================