-- You can change `derisk` to your actual metadata database name in your `.env` file
-- eg. `LOCAL_DB_NAME=derisk`

CREATE
DATABASE IF NOT EXISTS derisk;
use derisk;

-- For alembic migration tool
CREATE TABLE `alembic_version` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `version_num` varchar(32) NOT NULL COMMENT '版本号',
  `gmt_create` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_version` (`version_num`) BLOCK_SIZE 16384 GLOBAL
) AUTO_INCREMENT = 1 DEFAULT CHARSET = utf8mb4 COMMENT = 'alembic version table'

CREATE TABLE IF NOT EXISTS `knowledge_space`
(
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'auto increment id',
  `knowledge_id` varchar(100) NOT NULL COMMENT 'knowledge id',
  `name` varchar(100) NOT NULL COMMENT 'knowledge space name',
  `storage_type` varchar(50) NOT NULL COMMENT 'storage type',
  `tags` varchar(1024) DEFAULT NULL COMMENT 'knowledge tags',
  `domain_type` varchar(50) NOT NULL COMMENT 'domain type',
  `description` varchar(500) NOT NULL COMMENT 'description',
  `owner` varchar(100) DEFAULT NULL COMMENT 'owner',
  `context` text DEFAULT NULL COMMENT 'context argument',
  `gmt_create` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  `sys_code` varchar(100) DEFAULT NULL COMMENT 'sys code',
  PRIMARY KEY (`id`),
  KEY `idx_knowledge_id` (`knowledge_id`) BLOCK_SIZE 16384 GLOBAL COMMENT 'index:knowledge_id'
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='knowledge space table';

CREATE TABLE IF NOT EXISTS `knowledge_document`
(
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'auto increment id',
  `doc_id` varchar(100) NOT NULL COMMENT 'document id',
  `doc_name` varchar(100) NOT NULL COMMENT 'document path name',
  `doc_type` varchar(50) NOT NULL COMMENT 'doc type',
  `doc_token` varchar(100) DEFAULT NULL COMMENT 'doc token',
  `space` varchar(50) NOT NULL COMMENT 'knowledge space',
  `knowledge_id` varchar(100) NOT NULL COMMENT 'knowledge id',
  `chunk_size` int(11) NOT NULL COMMENT 'chunk size',
  `status` varchar(50) NOT NULL COMMENT 'status TODO,RUNNING,FAILED,FINISHED',
  `content` longtext NOT NULL COMMENT 'knowledge embedding sync result',
  `result` text DEFAULT NULL COMMENT 'knowledge content',
  `questions` text DEFAULT NULL COMMENT 'document related questions',
  `meta_data` text DEFAULT NULL COMMENT 'metadata info',
  `vector_ids` longtext DEFAULT NULL COMMENT 'vector_ids',
  `summary` longtext DEFAULT NULL COMMENT 'knowledge summary',
  `gmt_create` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  `chunk_params` text DEFAULT NULL COMMENT 'chunk params',
  PRIMARY KEY (`id`),
  KEY `idx_doc_id` (`doc_id`) BLOCK_SIZE 16384 GLOBAL COMMENT 'index:idx_doc_id'
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='knowledge document table';

CREATE TABLE IF NOT EXISTS `document_chunk`
(
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'auto increment id',
  `chunk_id` varchar(100) NOT NULL COMMENT 'chunk id',
  `doc_name` varchar(100) NOT NULL COMMENT 'document path name',
  `doc_type` varchar(50) DEFAULT NULL COMMENT 'doc type',
  `word_count` int(11) DEFAULT NULL COMMENT 'word count',
  `knowledge_id` varchar(100) DEFAULT NULL COMMENT 'knowledge id',
  `document_id` int(11) DEFAULT NULL COMMENT 'document parent id',
  `vector_id` varchar(100) DEFAULT NULL COMMENT 'vector id',
  `full_text_id` varchar(100) DEFAULT NULL COMMENT 'full text id',
  `content` longtext NOT NULL COMMENT 'chunk content',
  `questions` text DEFAULT NULL COMMENT 'chunk related questions',
  `meta_data` text DEFAULT NULL COMMENT 'metadata info',
  `gmt_create` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  `doc_id` varchar(100) DEFAULT NULL COMMENT 'doc_id',
  PRIMARY KEY (`id`),
  KEY `idx_chunk_id` (`chunk_id`) BLOCK_SIZE 16384 GLOBAL COMMENT 'index:chunk_id'
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='knowledge document chunk detail';

CREATE TABLE `knowledge_task` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `gmt_create` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `gmt_modified` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  `task_id` varchar(255) DEFAULT NULL COMMENT '任务id',
  `knowledge_id` varchar(255) DEFAULT NULL COMMENT '知识库id',
  `doc_type` varchar(255) DEFAULT NULL COMMENT '文档类型',
  `doc_content` text DEFAULT NULL COMMENT '文档的内容',
  `yuque_token` varchar(255) DEFAULT NULL COMMENT '语雀token',
  `group_login` varchar(255) DEFAULT NULL COMMENT '语雀group',
  `book_slug` varchar(255) DEFAULT NULL COMMENT '语雀book',
  `yuque_doc_id` varchar(255) DEFAULT NULL COMMENT '语雀文档id',
  `chunk_parameters` varchar(2048) DEFAULT NULL COMMENT '切分参数',
  `status` varchar(255) DEFAULT NULL COMMENT '状态',
  `owner` varchar(255) DEFAULT NULL COMMENT '任务发起者',
  `batch_id` varchar(255) DEFAULT NULL COMMENT '批次任务id',
  `doc_id` varchar(255) DEFAULT NULL COMMENT '文档表id',
  `retry_times` int(11) DEFAULT NULL COMMENT '重试次数',
  `error_msg` text DEFAULT NULL COMMENT '失败信息',
  `start_time` varchar(255) DEFAULT NULL COMMENT '任务开始时间',
  `end_time` varchar(255) DEFAULT NULL COMMENT '任务结束时间',
  `host` varchar(255) DEFAULT NULL COMMENT '任务执行机器',
  PRIMARY KEY (`id`),
  KEY `idx_task_id` (`task_id`) BLOCK_SIZE 16384 GLOBAL,
  KEY `idx_knowledge_id` (`knowledge_id`) BLOCK_SIZE 16384 GLOBAL,
  KEY `idx_status` (`status`) BLOCK_SIZE 16384 GLOBAL
) AUTO_INCREMENT = 1100001 DEFAULT CHARSET = utf8mb4  COMMENT = '知识任务表'

CREATE TABLE IF NOT EXISTS `connect_config`
(
    `id`       bigint(20)   NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
    `db_type`  varchar(255) NOT NULL COMMENT 'db type',
    `db_name`  varchar(255) NOT NULL COMMENT 'db name',
    `db_path`  varchar(255) DEFAULT NULL COMMENT 'file db path',
    `db_host`  varchar(255) DEFAULT NULL COMMENT 'db connect host(not file db)',
    `db_port`  varchar(255) DEFAULT NULL COMMENT 'db cnnect port(not file db)',
    `db_user`  varchar(255) DEFAULT NULL COMMENT 'db user',
    `db_pwd`   varchar(255) DEFAULT NULL COMMENT 'db password',
    `comment`  text COMMENT 'db comment',
    `sys_code` varchar(128) DEFAULT NULL COMMENT 'System code',
    `user_name`  varchar(255) DEFAULT NULL COMMENT 'user name',
    `user_id`  varchar(255) DEFAULT NULL COMMENT 'user id',
    `gmt_create` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    `gmt_modified` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record update time',
    `ext_config` text COMMENT 'Extended configuration, json format',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_db` (`db_name`),
    KEY        `idx_q_db_type` (`db_type`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT 'Connection confi';

CREATE TABLE IF NOT EXISTS `chat_history`
(
    `id`        bigint(20)   NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
    `conv_uid`  varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Conversation record unique id',
    `chat_mode` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Conversation scene mode',
    `summary`   longtext COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Conversation record summary',
    `user_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'interlocutor',
    `messages`  longtext COLLATE utf8mb4_unicode_ci COMMENT 'Conversation details',
    `message_ids` longtext COLLATE utf8mb4_unicode_ci COMMENT 'Message id list, split by comma',
    `app_code` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'App unique code',
    `sys_code`  varchar(128)                            DEFAULT NULL COMMENT 'System code',
    `gmt_create`  timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
    `gmt_modified` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
    UNIQUE KEY `conv_uid` (`conv_uid`),
    PRIMARY KEY (`id`),
    KEY `idx_chat_his_app_code` (`app_code`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Chat history';

CREATE TABLE IF NOT EXISTS `chat_history_message`
(
    `id`             bigint(20)             NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
    `conv_uid`       varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Conversation record unique id',
    `index_num`          int                                     NOT NULL COMMENT 'Message index',
    `round_index`    int                                     NOT NULL COMMENT 'Round of conversation',
    `message_detail` longtext COLLATE utf8mb4_unicode_ci COMMENT 'Message details, json format',
    `gmt_create`  timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
    `gmt_modified` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
    UNIQUE KEY `message_uid_index` (`conv_uid`, `index_num`),
    PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT 'Chat history message';


CREATE TABLE IF NOT EXISTS `chat_feed_back`
(
    `id`              bigint(20) NOT NULL AUTO_INCREMENT,
    `conv_uid`        varchar(128) DEFAULT NULL COMMENT 'Conversation ID',
    `conv_index`      int(4) DEFAULT NULL COMMENT 'Round of conversation',
    `score`           int(1) DEFAULT NULL COMMENT 'Score of user',
    `ques_type`       varchar(32)  DEFAULT NULL COMMENT 'User question category',
    `question`        longtext     DEFAULT NULL COMMENT 'User question',
    `knowledge_space` varchar(128) DEFAULT NULL COMMENT 'Knowledge space name',
    `messages`        longtext     DEFAULT NULL COMMENT 'The details of user feedback',
    `message_id`      varchar(255)  NULL COMMENT 'Message id',
    `feedback_type`   varchar(50)  NULL COMMENT 'Feedback type like or unlike',
    `reason_types`    varchar(255)  NULL COMMENT 'Feedback reason categories',
    `remark`          text          NULL COMMENT 'Feedback remark',
    `user_code`       varchar(128)  NULL COMMENT 'User code',
    `user_name`       varchar(128) DEFAULT NULL COMMENT 'User name',
    `gmt_create`     timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
    `gmt_modified`    timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_conv` (`conv_uid`,`conv_index`),
    KEY               `idx_conv` (`conv_uid`,`conv_index`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='User feedback table';


CREATE TABLE IF NOT EXISTS `my_plugin`
(
    `id`          bigint(20)                       NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
    `tenant`      varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'user tenant',
    `user_code`   varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'user code',
    `user_name`   varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'user name',
    `name`        varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'plugin name',
    `file_name`   varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'plugin package file name',
    `type`        varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin type',
    `version`     varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin version',
    `use_count`   int                                     DEFAULT NULL COMMENT 'plugin total use count',
    `succ_count`  int                                     DEFAULT NULL COMMENT 'plugin total success count',
    `sys_code`    varchar(128)                            DEFAULT NULL COMMENT 'System code',
    `gmt_create` TIMESTAMP                               DEFAULT CURRENT_TIMESTAMP COMMENT 'plugin install time',
    `gmt_modified`   TIMESTAMP                                DEFAULT CURRENT_TIMESTAMP COMMENT 'plugin upload time',
    PRIMARY KEY (`id`),
    UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User plugin table';

CREATE TABLE IF NOT EXISTS `plugin_hub`
(
    `id`              bigint(20)                              NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
    `name`            varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'plugin name',
    `description`     varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'plugin description',
    `author`          varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin author',
    `email`           varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin author email',
    `type`            varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin type',
    `version`         varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin version',
    `storage_channel` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin storage channel',
    `storage_url`     varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin download url',
    `download_param`  varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'plugin download param',
    `gmt_create`     TIMESTAMP                                DEFAULT CURRENT_TIMESTAMP COMMENT 'plugin upload time',
    `gmt_modified`   TIMESTAMP                                DEFAULT CURRENT_TIMESTAMP COMMENT 'plugin upload time',
    `installed`       int                                     DEFAULT NULL COMMENT 'plugin already installed count',
    PRIMARY KEY (`id`),
    UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Plugin Hub table';


CREATE TABLE IF NOT EXISTS `prompt_manage`
(
    `id`             bigint(20) NOT NULL AUTO_INCREMENT,
    `chat_scene`     varchar(100) DEFAULT NULL COMMENT 'Chat scene',
    `sub_chat_scene` varchar(100) DEFAULT NULL COMMENT 'Sub chat scene',
    `prompt_type`    varchar(100) DEFAULT NULL COMMENT 'Prompt type: common or private',
    `prompt_name`    varchar(256) DEFAULT NULL COMMENT 'prompt name',
    `prompt_code`    varchar(256) DEFAULT NULL COMMENT 'prompt code',
    `content`        longtext COMMENT 'Prompt content',
    `input_variables` varchar(1024) DEFAULT NULL COMMENT 'Prompt input variables(split by comma))',
    `response_schema` text  DEFAULT NULL COMMENT 'Prompt response schema',
    `model` varchar(128) DEFAULT NULL COMMENT 'Prompt model name(we can use different models for different prompt)',
    `prompt_language` varchar(32) DEFAULT NULL COMMENT 'Prompt language(eg:en, zh-cn)',
    `prompt_format` varchar(32) DEFAULT 'f-string' COMMENT 'Prompt format(eg: f-string, jinja2)',
    `prompt_desc`    varchar(512) DEFAULT NULL COMMENT 'Prompt description',
    `user_code`     varchar(128) DEFAULT NULL COMMENT 'User code',
    `user_name`      varchar(128) DEFAULT NULL COMMENT 'User name',
    `sys_code`       varchar(128)                            DEFAULT NULL COMMENT 'System code',
    `gmt_create`    timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
    `gmt_modified`   timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
    PRIMARY KEY (`id`),
    UNIQUE KEY `prompt_name_uiq` (`prompt_name`, `sys_code`, `prompt_language`, `model`),
    KEY              `gmt_create_idx` (`gmt_create`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Prompt management table';

CREATE TABLE IF NOT EXISTS `gpts_conversations` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` varchar(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `user_goal` text NOT NULL COMMENT 'User''s goals content',
  `conv_session_id` VARCHAR(255) DEFAULT NULL COMMENT 'Conversation session id',
  `gpts_name` varchar(255) NOT NULL COMMENT 'The gpts name',
  `state` varchar(255) DEFAULT NULL COMMENT 'The gpts state',
  `max_auto_reply_round` int(11) NOT NULL COMMENT 'max auto reply round',
  `auto_reply_count` int(11) NOT NULL COMMENT 'auto reply count',
  `user_code` varchar(255) DEFAULT NULL COMMENT 'user code',
  `sys_code` varchar(255) DEFAULT NULL COMMENT 'system app ',
  `gmt_create`    timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified`   timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  `team_mode` varchar(255) NULL COMMENT 'agent team work mode',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gpts_conversations` (`conv_id`),
  KEY `idx_gpts_name` (`gpts_name`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT="gpt conversations";

CREATE TABLE IF NOT EXISTS `gpts_instance` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `gpts_name` varchar(255) NOT NULL COMMENT 'Current AI assistant name',
  `gpts_describe` varchar(2255) NOT NULL COMMENT 'Current AI assistant describe',
  `resource_db` text COMMENT 'List of structured database names contained in the current gpts',
  `resource_internet` text COMMENT 'Is it possible to retrieve information from the internet',
  `resource_knowledge` text COMMENT 'List of unstructured database names contained in the current gpts',
  `gpts_agents` varchar(1000) DEFAULT NULL COMMENT 'List of agents names contained in the current gpts',
  `gpts_models` varchar(1000) DEFAULT NULL COMMENT 'List of llm model names contained in the current gpts',
  `language` varchar(100) DEFAULT NULL COMMENT 'gpts language',
  `user_code` varchar(255) NOT NULL COMMENT 'user code',
  `sys_code` varchar(255) DEFAULT NULL COMMENT 'system app code',
  `gmt_create`    timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified`   timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  `team_mode` varchar(255) NOT NULL COMMENT 'Team work mode',
  `is_sustainable` tinyint(1) NOT NULL COMMENT 'Applications for sustainable dialogue',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gpts` (`gpts_name`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT="gpts instance";

CREATE TABLE `gpts_messages` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` varchar(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `conv_session_id` VARCHAR(255) NOT NULL COMMENT 'Conversation session id',
  `message_id` VARCHAR(255) NOT NULL COMMENT 'The unique id of the message in the conversation', 
  `sender` varchar(255) NOT NULL COMMENT 'Who speaking in the current conversation turn',
  `receiver` varchar(255) NOT NULL COMMENT 'Who receive message in the current conversation turn',
  `sender_name` VARCHAR(255) NOT NULL COMMENT 'The name of the sender in the current conversation turn',
  `receiver_name` VARCHAR(255) NOT NULL COMMENT 'The name of the receiver in the current conversation turn',
  `model_name` varchar(255) DEFAULT NULL COMMENT 'message generate model',
  `rounds` int(11) NOT NULL COMMENT 'dialogue turns',
  `is_success` int(4)  NULL DEFAULT 0 COMMENT 'agent message is success',
  `app_code` varchar(255) NOT NULL COMMENT 'Current AI assistant code',
  `app_name` varchar(255) NOT NULL COMMENT 'Current AI assistant name',
  `thinking` TEXT DEFAULT NULL COMMENT 'Thinking content of the speech',
  `content` longtext COMMENT 'Content of the speech',
  `system_prompt` TEXT NULL COMMENT 'System prompt of the speech',
  `user_prompt` TEXT NULL COMMENT 'User prompt of the speech',
  `show_message` BOOLEAN DEFAULT 1 COMMENT 'Whether to display the message in the conversation',
  `goal_id` VARCHAR(255) DEFAULT NULL COMMENT 'The unique id of the goal in the conversation',
  `current_goal` text COMMENT 'The target corresponding to the current message',
  `context` text COMMENT 'Current conversation context',
  `review_info` longtext COMMENT 'Current conversation review info',
  `action_report` longtext COMMENT 'Current conversation action report',
  `resource_info` longtext DEFAULT NULL  COMMENT 'Current conversation resource info',
  `role` varchar(255) DEFAULT NULL COMMENT 'The role of the current message content',
  `avatar` VARCHAR(1024) DEFAULT NULL COMMENT 'Avatar URL of the sender',
  `gmt_create`    timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified`   timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  PRIMARY KEY (`id`),
  KEY `idx_q_messages` (`conv_id`,`rounds`,`sender`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT="gpts message";


CREATE TABLE `gpts_plans` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` varchar(255) NOT NULL COMMENT 'The unique id of the conversation record',
  `conv_round` int(11) NOT NULL COMMENT 'The dialogue turns',
  `conv_round_id` varchar(255) NOT NULL COMMENT 'The dialogue turns uid',
  `sub_task_id` varchar(255) NOT NULL COMMENT 'Subtask id',
  `task_parent` varchar(255) DEFAULT NULL COMMENT 'Subtask dependencies，like: 1,2,3',
  `sub_task_title` varchar(255) NOT NULL COMMENT 'subtask title',
  `sub_task_content` text NOT NULL COMMENT 'subtask content',
  `sub_task_agent` varchar(255) DEFAULT NULL COMMENT 'Available agents corresponding to subtasks',
  `resource_name` varchar(255) DEFAULT NULL COMMENT 'resource name',
  `agent_model` varchar(255) DEFAULT NULL COMMENT 'LLM model used by subtask processing agents',
  `retry_times` int(11) DEFAULT NULL COMMENT 'number of retries',
  `max_retry_times` int(11) DEFAULT NULL COMMENT 'Maximum number of retries',
  `state` varchar(255) DEFAULT NULL COMMENT 'subtask status',
  `result` longtext COMMENT 'subtask result',
  `gmt_create`    timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified`   timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sub_task` (`conv_id`,`sub_task_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT="gpt plan";

-- derisk.derisk_serve_flow definition
CREATE TABLE `derisk_serve_flow` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `uid` varchar(128) NOT NULL COMMENT 'Unique id',
  `dag_id` varchar(128) DEFAULT NULL COMMENT 'DAG id',
  `name` varchar(128) DEFAULT NULL COMMENT 'Flow name',
  `flow_data` longtext COMMENT 'Flow data, JSON format',
  `user_name` varchar(128) DEFAULT NULL COMMENT 'User name',
  `sys_code` varchar(128) DEFAULT NULL COMMENT 'System code',
  `flow_category` varchar(64) DEFAULT NULL COMMENT 'Flow category',
  `description` varchar(512) DEFAULT NULL COMMENT 'Flow description',
  `state` varchar(32) DEFAULT NULL COMMENT 'Flow state',
  `error_message` varchar(512) NULL comment 'Error message',
  `source` varchar(64) DEFAULT NULL COMMENT 'Flow source',
  `source_url` varchar(512) DEFAULT NULL COMMENT 'Flow source url',
  `version` varchar(32) DEFAULT NULL COMMENT 'Flow version',
  `define_type` varchar(32) null comment 'Flow define type(json or python)',
  `label_info` varchar(128) DEFAULT NULL COMMENT 'Flow label',
  `editable` int DEFAULT NULL COMMENT 'Editable, 0: editable, 1: not editable',
  `variables` text DEFAULT NULL COMMENT 'Flow variables, JSON format',
  `gmt_create`    timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'created time',
  `gmt_modified`   timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_uid` (`uid`),
  KEY `ix_derisk_serve_flow_sys_code` (`sys_code`),
  KEY `ix_derisk_serve_flow_uid` (`uid`),
  KEY `ix_derisk_serve_flow_dag_id` (`dag_id`),
  KEY `ix_derisk_serve_flow_user_name` (`user_name`),
  KEY `ix_derisk_serve_flow_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- derisk.derisk_serve_file definition
CREATE TABLE `derisk_serve_file` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `bucket` varchar(255) NOT NULL COMMENT 'Bucket name',
  `file_id` varchar(255) NOT NULL COMMENT 'File id',
  `file_name` varchar(256) NOT NULL COMMENT 'File name',
  `file_size` int DEFAULT NULL COMMENT 'File size',
  `storage_type` varchar(32) NOT NULL COMMENT 'Storage type',
  `storage_path` varchar(512) NOT NULL COMMENT 'Storage path',
  `uri` varchar(512) NOT NULL COMMENT 'File URI',
  `custom_metadata` text DEFAULT NULL COMMENT 'Custom metadata, JSON format',
  `file_hash` varchar(128) DEFAULT NULL COMMENT 'File hash',
  `user_name` varchar(128) DEFAULT NULL COMMENT 'User name',
  `sys_code` varchar(128) DEFAULT NULL COMMENT 'System code',
  `gmt_create` timestamp DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_bucket_file_id` (`bucket`, `file_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- derisk.derisk_serve_variables definition
CREATE TABLE `derisk_serve_variables` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `key_info` varchar(128) NOT NULL COMMENT 'Variable key',
  `name` varchar(128) DEFAULT NULL COMMENT 'Variable name',
  `label_info` varchar(128) DEFAULT NULL COMMENT 'Variable label',
  `value` text DEFAULT NULL COMMENT 'Variable value, JSON format',
  `value_type` varchar(32) DEFAULT NULL COMMENT 'Variable value type(string, int, float, bool)',
  `category` varchar(32) DEFAULT 'common' COMMENT 'Variable category(common or secret)',
  `encryption_method` varchar(32) DEFAULT NULL COMMENT 'Variable encryption method(fernet, simple, rsa, aes)',
  `salt` varchar(128) DEFAULT NULL COMMENT 'Variable salt',
  `scope` varchar(32) DEFAULT 'global' COMMENT 'Variable scope(global,flow,app,agent,datasource,flow_priv,agent_priv, ""etc)',
  `scope_key` varchar(256) DEFAULT NULL COMMENT 'Variable scope key, default is empty, for scope is "flow_priv", the scope_key is dag id of flow',
  `enabled` int DEFAULT 1 COMMENT 'Variable enabled, 0: disabled, 1: enabled',
  `description` text DEFAULT NULL COMMENT 'Variable description',
  `user_name` varchar(128) DEFAULT NULL COMMENT 'User name',
  `sys_code` varchar(128) DEFAULT NULL COMMENT 'System code',
  `gmt_create` timestamp DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  KEY `ix_your_table_name_key` (`key_info`),
  KEY `ix_your_table_name_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `derisk_serve_model` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `host` varchar(255) NOT NULL COMMENT 'The model worker host',
  `port` int NOT NULL COMMENT 'The model worker port',
  `model` varchar(255) NOT NULL COMMENT 'The model name',
  `provider` varchar(255) NOT NULL COMMENT 'The model provider',
  `worker_type` varchar(255) NOT NULL COMMENT 'The worker type',
  `params` text NOT NULL COMMENT 'The model parameters, JSON format',
  `enabled` int DEFAULT 1 COMMENT 'Whether the model is enabled, if it is enabled, it will be started when the system starts, 1 is enabled, 0 is disabled',
  `worker_name` varchar(255) DEFAULT NULL COMMENT 'The worker name',
  `description` text DEFAULT NULL COMMENT 'The model description',
  `user_name` varchar(128) DEFAULT NULL COMMENT 'User name',
  `sys_code` varchar(128) DEFAULT NULL COMMENT 'System code',
  `gmt_create` timestamp DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  KEY `idx_user_name` (`user_name`),
  KEY `idx_sys_code` (`sys_code`),
  UNIQUE KEY `uk_model_provider_type` (`model`, `provider`, `worker_type`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Model persistence table';

-- derisk.gpts_app definition
CREATE TABLE `gpts_app` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `app_code` varchar(255) NOT NULL COMMENT 'Current AI assistant code',
  `app_name` varchar(255) NOT NULL COMMENT 'Current AI assistant name',
  `app_describe` varchar(2255) NOT NULL COMMENT 'Current AI assistant describe',
  `language` varchar(100) NOT NULL COMMENT 'gpts language',
  `team_mode` varchar(255) NOT NULL COMMENT 'Team work mode',
  `team_context` text COMMENT 'The execution logic and team member content that teams with different working modes rely on',
  `user_code` varchar(255) DEFAULT NULL COMMENT 'user code',
  `sys_code` varchar(255) DEFAULT NULL COMMENT 'system app code',
  `icon` varchar(1024) DEFAULT NULL COMMENT 'app icon, url',
  `published` varchar(64) DEFAULT 'false' COMMENT 'Has it been published?',
  `param_need` text DEFAULT NULL COMMENT 'Parameter information supported by the application',
  `admins` text DEFAULT NULL COMMENT 'administrator',
  `gmt_create` timestamp DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gpts_app` (`app_name`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `gpts_app_collection` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `app_code` varchar(255) NOT NULL COMMENT 'Current AI assistant code',
  `user_code` int(11) NOT NULL COMMENT 'user code',
  `sys_code` varchar(255) NULL COMMENT 'system app code',
  `gmt_create` timestamp DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  KEY `idx_app_code` (`app_code`),
  KEY `idx_user_code` (`user_code`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT="gpt collections";

-- derisk.gpts_app_detail definition
CREATE TABLE `gpts_app_detail` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `app_code` varchar(255) NOT NULL COMMENT 'Current AI assistant code',
  `app_name` varchar(255) NOT NULL COMMENT 'Current AI assistant name',
  `type`  varchar(255) NOT NULL COMMENT 'detail agent link type',
  `agent_name` varchar(255) NOT NULL COMMENT ' Agent name',
  `agent_role` varchar(255) NOT NULL COMMENT ' 当前关联Agent角色或应用名称',
  `agent_describe` text DEFAULT NULL COMMENT ' 当前关联Agent或者应用的职责功能描述',
  `node_id` varchar(255) NOT NULL COMMENT 'Current AI assistant Agent Node id',
  `resources` text COMMENT 'Agent bind  resource',
  `prompt_template` text COMMENT 'Agent bind  template',
  `llm_strategy` varchar(25) DEFAULT NULL COMMENT 'Agent use llm strategy',
  `llm_strategy_value` text COMMENT 'Agent use llm strategy value',
  `gmt_create` timestamp DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_gpts_app_agent_node` (`app_name`,`agent_name`,`node_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- For deploy model cluster of DERISK(StorageModelRegistry)
CREATE TABLE IF NOT EXISTS `derisk_cluster_registry_instance` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `model_name` varchar(128) NOT NULL COMMENT 'Model name',
  `host` varchar(128) NOT NULL COMMENT 'Host of the model',
  `port` int(11) NOT NULL COMMENT 'Port of the model',
  `weight` float DEFAULT 1.0 COMMENT 'Weight of the model',
  `check_healthy` tinyint(1) DEFAULT 1 COMMENT 'Whether to check the health of the model',
  `healthy` tinyint(1) DEFAULT 0 COMMENT 'Whether the model is healthy',
  `enabled` tinyint(1) DEFAULT 1 COMMENT 'Whether the model is enabled',
  `prompt_template` varchar(128) DEFAULT NULL COMMENT 'Prompt template for the model instance',
  `last_heartbeat` datetime DEFAULT NULL COMMENT 'Last heartbeat time of the model instance',
  `user_name` varchar(128) DEFAULT NULL COMMENT 'User name',
  `sys_code` varchar(128) DEFAULT NULL COMMENT 'System code',
  `gmt_create` timestamp DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_model_instance` (`model_name`, `host`, `port`, `sys_code`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COMMENT='Cluster model instance table, for registering and managing model instances';

-- derisk.recommend_question definition
CREATE TABLE `recommend_question` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `gmt_create` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'last update time',
  `app_code` varchar(255) NOT NULL COMMENT 'Current AI assistant code',
  `question` text DEFAULT NULL COMMENT 'question',
  `user_code` varchar(255) NOT NULL COMMENT 'user code',
  `sys_code` varchar(255) NULL COMMENT 'system app code',
  `valid` varchar(10) DEFAULT 'true' COMMENT 'is it effective，true/false',
  `chat_mode` varchar(255) DEFAULT NULL COMMENT 'Conversation scene mode，chat_knowledge...',
  `params` text DEFAULT NULL COMMENT 'question param',
  `is_hot_question` varchar(10) DEFAULT 'false' COMMENT 'Is it a popular recommendation question?',
  PRIMARY KEY (`id`),
  KEY `idx_rec_q_app_code` (`app_code`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT="AI application related recommendation issues";

-- derisk.user_recent_apps definition
CREATE TABLE `user_recent_apps` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `gmt_create` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  `gmt_modified` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'last update time',
  `app_code` varchar(255) NOT NULL COMMENT 'AI assistant code',
  `last_accessed` timestamp NULL DEFAULT NULL COMMENT 'User recent usage time',
  `user_code` varchar(255) DEFAULT NULL COMMENT 'user code',
  `sys_code` varchar(255) DEFAULT NULL COMMENT 'system app code',
  PRIMARY KEY (`id`),
  KEY `idx_user_r_app_code` (`app_code`),
  KEY `idx_last_accessed` (`last_accessed`),
  KEY `idx_user_code` (`user_code`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User recently used apps';

-- derisk.derisk_serve_derisks_my definition
CREATE TABLE `derisk_serve_derisks_my` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `name` varchar(255)  NOT NULL COMMENT 'plugin name',
  `user_code` varchar(255)  DEFAULT NULL COMMENT 'user code',
  `user_name` varchar(255)  DEFAULT NULL COMMENT 'user name',
  `file_name` varchar(255)  NOT NULL COMMENT 'plugin package file name',
  `type` varchar(255)  DEFAULT NULL COMMENT 'plugin type',
  `version` varchar(255)  DEFAULT NULL COMMENT 'plugin version',
  `use_count` int DEFAULT NULL COMMENT 'plugin total use count',
  `succ_count` int DEFAULT NULL COMMENT 'plugin total success count',
  `sys_code` varchar(128) DEFAULT NULL COMMENT 'System code',
  `gmt_create` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'plugin install time',
  `gmt_modified` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`, `user_name`),
  KEY `ix_my_plugin_sys_code` (`sys_code`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- derisk.derisk_serve_derisks_hub definition
CREATE TABLE `derisk_serve_derisks_hub` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `name` varchar(255) NOT NULL COMMENT 'plugin name',
  `description` varchar(255)  NULL COMMENT 'plugin description',
  `author` varchar(255) DEFAULT NULL COMMENT 'plugin author',
  `email` varchar(255) DEFAULT NULL COMMENT 'plugin author email',
  `type` varchar(255) DEFAULT NULL COMMENT 'plugin type',
  `version` varchar(255) DEFAULT NULL COMMENT 'plugin version',
  `storage_channel` varchar(255) DEFAULT NULL COMMENT 'plugin storage channel',
  `storage_url` varchar(255) DEFAULT NULL COMMENT 'plugin download url',
  `download_param` varchar(255) DEFAULT NULL COMMENT 'plugin download param',
  `gmt_create` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'plugin upload time',
  `gmt_modified` TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'update time',
  `installed` int DEFAULT NULL COMMENT 'plugin already installed count',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
