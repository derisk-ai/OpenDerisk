#!/usr/bin/env node

/**
 * Post-install script for OpenDerisk npm package
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const INSTALL_DIR = process.env.OPENDERISK_INSTALL_DIR || path.join(os.homedir(), '.openderisk');
const REPO_URL = 'https://github.com/derisk-ai/OpenDerisk.git';

const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m'
};

function log(message) {
  console.log(`${colors.cyan}[openderisk]${colors.reset} ${message}`);
}

function success(message) {
  console.log(`${colors.green}[openderisk]${colors.reset} ${message}`);
}

function warn(message) {
  console.log(`${colors.yellow}[openderisk]${colors.reset} ${message}`);
}

function commandExists(command) {
  try {
    execSync(`which ${command}`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function installUv() {
  if (commandExists('uv')) {
    return;
  }

  log('Installing uv package manager...');
  try {
    execSync('curl -LsSf https://astral.sh/uv/install.sh | sh', {
      stdio: 'inherit',
      shell: true
    });
    success('uv installed successfully');
  } catch (err) {
    warn('Failed to install uv automatically');
    warn('Please install manually: https://github.com/astral-sh/uv');
  }
}

function cloneRepo() {
  if (fs.existsSync(path.join(INSTALL_DIR, '.git'))) {
    log('OpenDerisk already exists, skipping clone');
    return;
  }

  log('Cloning OpenDerisk repository...');
  const parentDir = path.dirname(INSTALL_DIR);
  
  if (!fs.existsSync(parentDir)) {
    fs.mkdirSync(parentDir, { recursive: true });
  }

  try {
    execSync(`git clone --depth 1 ${REPO_URL} "${INSTALL_DIR}"`, {
      stdio: 'inherit'
    });
    success('Repository cloned successfully');
  } catch (err) {
    warn('Failed to clone repository automatically');
    warn(`You can manually clone: git clone ${REPO_URL} ${INSTALL_DIR}`);
  }
}

function main() {
  console.log('');
  log('Setting up OpenDerisk...');
  console.log('');

  installUv();
  cloneRepo();

  console.log('');
  success('Setup complete! 🎉');
  console.log('');
  console.log('Next steps:');
  console.log('  1. Configure API keys in:');
  console.log(`     ${path.join(INSTALL_DIR, 'configs/derisk-proxy-aliyun.toml')}`);
  console.log('  2. Run: openderisk --help');
  console.log('  3. Start server: openderisk-server');
  console.log('');
  console.log('Documentation: https://github.com/derisk-ai/OpenDerisk');
  console.log('');
}

main();
