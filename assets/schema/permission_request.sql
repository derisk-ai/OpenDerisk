-- Permission Request Table
-- This table stores user requests for role assignments and permission grants

CREATE TABLE IF NOT EXISTS `permission_request` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL COMMENT '申请人 user.id',
    `request_type` VARCHAR(32) NOT NULL COMMENT '申请类型: role_assign/permission_grant/account_activation',
    `role_id` INT NULL COMMENT '申请的角色ID (request_type=role_assign)',
    `resource_type` VARCHAR(64) NULL COMMENT '资源类型 (request_type=permission_grant)',
    `resource_id` VARCHAR(255) NULL COMMENT '资源ID (request_type=permission_grant)',
    `action` VARCHAR(32) NULL COMMENT '操作类型 (request_type=permission_grant)',
    `reason` TEXT NULL COMMENT '申请理由',
    `status` VARCHAR(16) DEFAULT 'pending' COMMENT '状态: pending/approved/rejected/cancelled',
    `reviewer_id` INT NULL COMMENT '审批人 user.id',
    `review_comment` TEXT NULL COMMENT '审批意见',
    `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `gmt_review` DATETIME NULL COMMENT '审批时间',
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_reviewer_id` (`reviewer_id`),
    INDEX `idx_request_type` (`request_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='权限申请表';