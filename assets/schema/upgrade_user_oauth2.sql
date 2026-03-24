-- ============================================================
-- OAuth2 User Table Extension
-- Adds oauth_provider, oauth_id, email, avatar columns to user table
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- Table: user - Add OAuth2 columns
-- Run this once. If columns already exist, ALTER will fail (safe to ignore).
ALTER TABLE `user` ADD COLUMN `oauth_provider` VARCHAR(64) NULL COMMENT 'OAuth2 provider (e.g. github, custom)';
ALTER TABLE `user` ADD COLUMN `oauth_id` VARCHAR(255) NULL COMMENT 'User ID from OAuth provider';
ALTER TABLE `user` ADD COLUMN `email` VARCHAR(255) NULL COMMENT 'User email';
ALTER TABLE `user` ADD COLUMN `avatar` VARCHAR(512) NULL COMMENT 'Avatar URL';
ALTER TABLE `user` ADD UNIQUE KEY `uk_oauth_provider_id` (`oauth_provider`, `oauth_id`);

SET FOREIGN_KEY_CHECKS = 1;
