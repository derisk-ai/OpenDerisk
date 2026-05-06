-- ============================================================
-- Local Authentication Extension
-- Adds password_hash column to user table for local login
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- Table: user - Add password_hash column for local authentication
-- Run this once. If column already exists, ALTER will fail (safe to ignore).
ALTER TABLE `user` ADD COLUMN `password_hash` VARCHAR(255) NULL COMMENT 'bcrypt hashed password for local auth';

SET FOREIGN_KEY_CHECKS = 1;
