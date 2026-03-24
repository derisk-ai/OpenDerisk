-- Upgrade script: extend custom_variables column from VARCHAR(2000) to TEXT
-- Issue: Data too long for column 'custom_variables' when saving agent configs
-- Date: 2026-03-23

-- For MySQL/MariaDB
ALTER TABLE `gpts_app_config` MODIFY COLUMN `custom_variables` TEXT NULL COMMENT '当前版本配置自定义参数配置';
