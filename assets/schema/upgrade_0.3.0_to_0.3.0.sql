-- ============================================================
-- Incremental DDL Script for Derisk
-- Upgrade from version 0.3.0 to 0.3.0
-- Generated: 2026-02-27 15:25:08
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- New Tables
-- ============================================================

-- Table: gpts_kanban (NEW)
CREATE TABLE IF NOT EXISTS `gpts_kanban` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `mission` TEXT NOT NULL COMMENT 'Mission description',
  `stages` LONGTEXT NULL COMMENT 'Stages data (JSON)',
  PRIMARY KEY (`id`),
  KEY `idx_kanban_conv_session` (`conv_id`, `session_id`),
  KEY `idx_pre_kanban_log_conv_session` (`conv_id`, `session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_pre_kanban_log (NEW)
CREATE TABLE IF NOT EXISTS `gpts_pre_kanban_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `agent_id` VARCHAR(255) NOT NULL COMMENT 'The agent id',
  PRIMARY KEY (`id`),
  KEY `idx_pre_kanban_log_conv_session` (`conv_id`, `session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: gpts_work_log (NEW)
CREATE TABLE IF NOT EXISTS `gpts_work_log` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `tool` VARCHAR(255) NOT NULL COMMENT 'Tool name',
  `args` TEXT NULL COMMENT 'Tool arguments (JSON)',
  `summary` TEXT NULL COMMENT 'Brief summary of the action',
  `result` LONGTEXT NULL COMMENT 'Result content',
  `archives` TEXT NULL COMMENT 'List of archive file keys (JSON)',
  `tags` TEXT NULL COMMENT 'Tags (JSON array)',
  `tokens` INT NOT NULL DEFAULT 0 COMMENT 'Estimated token count',
  PRIMARY KEY (`id`),
  KEY `idx_work_log_conv_session` (`conv_id`, `session_id`),
  KEY `idx_work_log_conv_tool` (`conv_id`, `tool`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: user (NEW)
CREATE TABLE IF NOT EXISTS `user` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(50) NULL,
  `fullname` VARCHAR(50) NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Modified Tables
-- ============================================================

-- Table: connect_config
ALTER TABLE `connect_config` ADD COLUMN `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
-- ALTER TABLE `connect_config` DROP COLUMN `ext_config`;
-- ALTER TABLE `connect_config` DROP COLUMN `gmt_create`;
-- ALTER TABLE `connect_config` DROP COLUMN `id`;

-- Table: derisk_cluster_registry_instance
ALTER TABLE `derisk_cluster_registry_instance` MODIFY COLUMN `weight` FLOAT NULL COMMENT 'Weight of the model';

-- Table: gpts_app_config
ALTER TABLE `gpts_app_config` MODIFY COLUMN `ext_config` TEXT NULL COMMENT '当前版本配置的扩展配置，各自动态扩展的内容';

-- Table: gpts_conversations
ALTER TABLE `gpts_conversations` MODIFY COLUMN `sys_code` VARCHAR(255) NULL COMMENT 'system app ';
ALTER TABLE `gpts_conversations` MODIFY COLUMN `user_goal` TEXT NOT NULL COMMENT 'User';
ALTER TABLE `gpts_conversations` MODIFY COLUMN `vis_render` VARCHAR(255) NULL COMMENT 'vis mode of chat conversation ';
-- ALTER TABLE `gpts_conversations` DROP COLUMN `conv_id`;
-- ALTER TABLE `gpts_conversations` DROP COLUMN `conv_session_id`;
-- ALTER TABLE `gpts_conversations` DROP COLUMN `gmt_create`;
-- ALTER TABLE `gpts_conversations` DROP COLUMN `gmt_modified`;
-- ALTER TABLE `gpts_conversations` DROP COLUMN `max_auto_reply_round`;
-- ALTER TABLE `gpts_conversations` DROP COLUMN `team_mode`;

-- Table: gpts_messages_system
ALTER TABLE `gpts_messages_system` MODIFY COLUMN `content` TEXT NULL COMMENT '消息内容';
ALTER TABLE `gpts_messages_system` MODIFY COLUMN `content_extra` VARCHAR(2000) NULL COMMENT '消息扩展内容，根据类型阶段不同，内容不同';

-- Table: gpts_plans
ALTER TABLE `gpts_plans` MODIFY COLUMN `result` TEXT NULL COMMENT 'subtask result';
ALTER TABLE `gpts_plans` MODIFY COLUMN `task_round_description` VARCHAR(500) NULL COMMENT 'task round description.(Can be empty if there are no multiple tasks in a round)';
ALTER TABLE `gpts_plans` MODIFY COLUMN `task_round_title` VARCHAR(255) NULL COMMENT 'task round title.(Can be empty if there are no multiple tasks in a round)';
-- ALTER TABLE `gpts_plans` DROP COLUMN `agent_model`;
-- ALTER TABLE `gpts_plans` DROP COLUMN `conv_id`;
-- ALTER TABLE `gpts_plans` DROP COLUMN `conv_session_id`;
-- ALTER TABLE `gpts_plans` DROP COLUMN `gmt_create`;
-- ALTER TABLE `gpts_plans` DROP COLUMN `gmt_modified`;
-- ALTER TABLE `gpts_plans` DROP COLUMN `max_retry_times`;
-- ALTER TABLE `gpts_plans` DROP COLUMN `planning_agent`;
-- ALTER TABLE `gpts_plans` DROP COLUMN `planning_model`;
-- ALTER TABLE `gpts_plans` DROP COLUMN `sub_task_agent`;

-- Table: gpts_tool
ALTER TABLE `gpts_tool` DROP INDEX `idx_tool_id`;
ALTER TABLE `gpts_tool` ADD INDEX `idx_tool_detail_id` (`tool_id`);
ALTER TABLE `gpts_tool` ADD INDEX `idx_tool_name` (`tool_id`);

-- Table: gpts_tool_detail
ALTER TABLE `gpts_tool_detail` DROP INDEX `idx_tool_id`;
ALTER TABLE `gpts_tool_detail` ADD INDEX `idx_tool_detail_id` (`tool_id`);

-- ============================================================
-- Removed Tables (commented out for safety)
-- ============================================================

-- DROP TABLE IF EXISTS `derisk_serve_channel_config`;
-- DROP TABLE IF EXISTS `derisk_serve_config`;
-- DROP TABLE IF EXISTS `derisk_serve_cron_job`;
-- DROP TABLE IF EXISTS `derisk_serve_file`;
-- DROP TABLE IF EXISTS `derisk_serve_flow`;
-- DROP TABLE IF EXISTS `derisk_serve_mcp`;
-- DROP TABLE IF EXISTS `derisk_serve_model`;
-- DROP TABLE IF EXISTS `derisk_serve_variables`;
-- DROP TABLE IF EXISTS `gpts_app`;
-- DROP TABLE IF EXISTS `gpts_app_detail`;
-- DROP TABLE IF EXISTS `server_app_skill`;


SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- End of Incremental DDL Script
-- ============================================================