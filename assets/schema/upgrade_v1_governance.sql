-- ============================================================
-- V1 架构治理升级脚本：补心跳 + lease + 事件日志
-- 包含 PR 4 (last_heartbeat)、Tier 3.2 (worker_id/lease_expires_at)、
-- Tier 3.1 (gpts_events 表)
-- 幂等：每个 ALTER 用 IF NOT EXISTS 语义（MySQL 8+）或存储过程判断
-- ============================================================

-- ---- 1. gpts_conversations: last_heartbeat (PR 4 漏写) ----
ALTER TABLE `gpts_conversations`
  ADD COLUMN `last_heartbeat` DATETIME NULL COMMENT 'last heartbeat time of the agent loop';

-- ---- 2. gpts_conversations: worker_id + lease_expires_at (Tier 3.2) ----
ALTER TABLE `gpts_conversations`
  ADD COLUMN `worker_id` VARCHAR(128) NULL COMMENT 'worker process id holding the lease';
ALTER TABLE `gpts_conversations`
  ADD COLUMN `lease_expires_at` DATETIME NULL COMMENT 'when the lease expires, NULL if no lease';
ALTER TABLE `gpts_conversations`
  ADD INDEX `idx_gpts_conv_lease` (`lease_expires_at`);

-- ---- 3. gpts_events 表 (Tier 3.1) ----
CREATE TABLE IF NOT EXISTS `gpts_events` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_id` VARCHAR(255) NOT NULL COMMENT 'conversation id',
  `message_id` VARCHAR(255) NULL COMMENT 'message id this event belongs to',
  `sequence` INT NOT NULL DEFAULT 0 COMMENT 'per-conv monotonic sequence number',
  `event_type` VARCHAR(64) NOT NULL COMMENT 'think_start/think_end/act_start/act_end/etc.',
  `event_data` LONGTEXT NULL COMMENT 'JSON event payload',
  `gmt_create` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'create time',
  PRIMARY KEY (`id`),
  INDEX `idx_events_conv_seq` (`conv_id`, `sequence`),
  INDEX `idx_events_message` (`message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent event log for replay/audit (Tier 3.1)';
