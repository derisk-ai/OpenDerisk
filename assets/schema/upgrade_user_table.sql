-- Upgrade script: Add OAuth and role columns to user table
-- Run this if user table exists but missing columns for OAuth user management

-- Add columns if not exists (MySQL 8.0+)
ALTER TABLE `user`
    ADD COLUMN IF NOT EXISTS `oauth_provider` VARCHAR(64) NULL COMMENT 'OAuth2 provider',
    ADD COLUMN IF NOT EXISTS `oauth_id` VARCHAR(255) NULL COMMENT 'OAuth provider user ID',
    ADD COLUMN IF NOT EXISTS `email` VARCHAR(255) NULL COMMENT 'User email',
    ADD COLUMN IF NOT EXISTS `avatar` VARCHAR(512) NULL COMMENT 'Avatar URL',
    ADD COLUMN IF NOT EXISTS `role` VARCHAR(20) NULL DEFAULT 'normal' COMMENT 'User role: normal/admin',
    ADD COLUMN IF NOT EXISTS `is_active` INT NOT NULL DEFAULT 1 COMMENT '1=active, 0=disabled',
    ADD INDEX IF NOT EXISTS `idx_oauth` (`oauth_provider`, `oauth_id`);

-- For older MySQL versions, use separate statements:
-- ALTER TABLE `user` ADD COLUMN `oauth_provider` VARCHAR(64) NULL COMMENT 'OAuth2 provider';
-- ALTER TABLE `user` ADD COLUMN `oauth_id` VARCHAR(255) NULL COMMENT 'OAuth provider user ID';
-- ALTER TABLE `user` ADD COLUMN `email` VARCHAR(255) NULL COMMENT 'User email';
-- ALTER TABLE `user` ADD COLUMN `avatar` VARCHAR(512) NULL COMMENT 'Avatar URL';
-- ALTER TABLE `user` ADD COLUMN `role` VARCHAR(20) NULL DEFAULT 'normal' COMMENT 'User role: normal/admin';
-- ALTER TABLE `user` ADD COLUMN `is_active` INT NOT NULL DEFAULT 1 COMMENT '1=active, 0=disabled';
-- ALTER TABLE `user` ADD INDEX `idx_oauth` (`oauth_provider`, `oauth_id`);
