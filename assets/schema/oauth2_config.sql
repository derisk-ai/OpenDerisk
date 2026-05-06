-- OAuth2 Configuration Table
-- Stores OAuth2 settings in database for persistence across deployments
-- Note: client_secret is stored in plain text and masked when displayed

CREATE TABLE IF NOT EXISTS `oauth2_config` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  `config_key` VARCHAR(64) NOT NULL COMMENT 'Configuration key (default: global)',
  `enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'OAuth2 enabled flag',
  `providers_json` TEXT NULL COMMENT 'OAuth2 providers configuration (JSON array)',
  `admin_users_json` TEXT NULL COMMENT 'Admin users list (JSON array)',
  `default_role` VARCHAR(32) NULL DEFAULT 'viewer' COMMENT 'Default RBAC role for new OAuth2 users',
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Modify time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_config_key` (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='OAuth2 configuration storage (client_secret masked on display)';
