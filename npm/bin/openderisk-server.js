#!/usr/bin/env node

/**
 * OpenDerisk Server Launcher
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const INSTALL_DIR = process.env.OPENDERISK_INSTALL_DIR || path.join(os.homedir(), '.openderisk');

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  blue: '\x1b[34m'
};

function log(message) {
  console.log(`${colors.blue}[OpenDerisk Server]${colors.reset} ${message}`);
}

function error(message) {
  console.error(`${colors.red}[Error]${colors.reset} ${message}`);
  process.exit(1);
}

function main() {
  if (!fs.existsSync(INSTALL_DIR)) {
    error('OpenDerisk not installed. Please run: npm install -g openderisk');
  }

  log('Starting OpenDerisk Server...');
  log(`Config: ${path.join(INSTALL_DIR, 'configs/derisk-proxy-aliyun.toml')}`);

  const uvPath = path.join(os.homedir(), '.local/bin/uv');
  const pythonCmd = fs.existsSync(uvPath) ? uvPath : 'uv';

  const child = spawn(pythonCmd, ['run', 'derisk', 'start', 'webserver', ...process.argv.slice(2)], {
    cwd: INSTALL_DIR,
    stdio: 'inherit',
    env: process.env
  });

  child.on('error', (err) => {
    error(`Failed to start server: ${err.message}`);
  });

  child.on('exit', (code) => {
    process.exit(code || 0);
  });
}

main();
