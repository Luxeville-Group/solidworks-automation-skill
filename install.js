#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const os = require('os');

const SKILL_NAME = 'solidworks-automation';
const REPO_URL = 'https://github.com/Luxeville-Group/solidworks-automation-skill.git';

// Detect existing skill directories.
function getAllSkillsDirs() {
  const homeDir = os.homedir();
  const possibleDirs = [
    path.join(homeDir, '.agents', 'skills'),
    path.join(homeDir, '.claude', 'skills'),
    path.join(homeDir, '.codex', 'skills'),
    path.join(homeDir, '.cursor', 'skills'),
    path.join(homeDir, '.openclaw', 'skills'),
  ];

  const existingDirs = possibleDirs.filter(dir => fs.existsSync(dir));

  // Create default OpenClaw/Codex directories when none exist.
  if (existingDirs.length === 0) {
    const bootstrapDirs = [
      path.join(homeDir, '.codex', 'skills'),
      path.join(homeDir, '.openclaw', 'skills'),
    ];

    bootstrapDirs.forEach(dir => fs.mkdirSync(dir, { recursive: true }));
    return bootstrapDirs;
  }

  return existingDirs;
}

// Install or update in one directory.
function installToDir(skillsDir) {
  const targetDir = path.join(skillsDir, SKILL_NAME);

  console.log(`\n📁 Hedef dizin / Target directory: ${targetDir}`);

  // Check for an existing installation.
  if (fs.existsSync(targetDir)) {
    console.log('⚠️  Skill mevcut, güncelleniyor / Updating existing skill...');
    try {
      const remote = execFileSync('git', ['remote', 'get-url', 'origin'], { cwd: targetDir, encoding: 'utf8' }).trim();
      if (!/^(?:https:\/\/github\.com\/|git@github\.com:)Luxeville-Group\/solidworks-automation-skill(?:\.git)?\/?$/i.test(remote)) {
        console.error('Mevcut kurulum bu fork deposuna ait değil / Existing installation belongs to another repository. Choose a new skill directory.');
        return false;
      }
      execFileSync('git', ['pull', '--ff-only', 'origin'], { cwd: targetDir, stdio: 'inherit' });
      console.log('✅ Güncellendi / Updated!');
      return true;
    } catch (error) {
      console.log('⚠️  Güncelleme başarısız / Update failed; existing files retained.');
      return false;
    }
  }

  // Clone with argument arrays rather than shell interpolation.
  try {
    console.log('📦 İndiriliyor / Downloading...');
    execFileSync('git', ['clone', REPO_URL, targetDir], { stdio: 'inherit' });
    console.log('✅ Kuruldu / Installed!');
  return true;
  } catch (error) {
    console.error(`❌ Kurulum başarısız / Installation failed: ${error.message}`);
    return false;
  }
}

function selectPrimaryInstallDir(installedDirs) {
  const priority = [
    path.join('.codex', 'skills'),
    path.join('.claude', 'skills'),
    path.join('.agents', 'skills'),
    path.join('.openclaw', 'skills'),
    path.join('.cursor', 'skills'),
  ];

  for (const marker of priority) {
    const found = installedDirs.find(dir => dir.includes(marker));
    if (found) {
      return found;
    }
  }

  return installedDirs[0];
}

function registerMcpForAiClients(installedDirs) {
  if (installedDirs.length === 0) {
    return;
  }

  const primaryDir = selectPrimaryInstallDir(installedDirs);
  const registerScript = path.join(primaryDir, 'mcp-server', 'register_all_ai_mcp.js');

  if (!fs.existsSync(registerScript)) {
    console.log(`⚠️  MCP kayıt betiği bulunamadı / MCP registration script not found: ${registerScript}`);
    return;
  }

  console.log('\n🔌 MCP, AI istemcilerine kaydediliyor / Registering MCP with AI clients...');
  try {
    execFileSync('node', [registerScript, '--install-dependencies'], { stdio: 'inherit' });
  } catch (error) {
    console.log('⚠️  MCP kaydı tamamlanamadı; elle çalıştırın / Registration incomplete; run manually:');
    console.log(`  node "${registerScript}" --install-dependencies`);
  }
}

function install() {
  console.log('🚀 SolidWorks Automation Skill kuruluyor / Installing...\n');

  const skillsDirs = getAllSkillsDirs();
  console.log(`Bulunan / Found ${skillsDirs.length} AI aracı dizini / AI tool directories:\n${skillsDirs.map(d => `  - ${d}`).join('\n')}\n`);

  let successCount = 0;
  const installedDirs = [];
  for (const dir of skillsDirs) {
    if (installToDir(dir)) {
      successCount++;
      installedDirs.push(path.join(dir, SKILL_NAME));
    }
  }

  // Install Python dependencies once.
  if (successCount > 0) {
    console.log('\n📦 Temel Python bağımlılıkları kuruluyor / Installing base Python dependencies...');
    try {
      execFileSync('pip', ['install', 'pywin32>=305', 'comtypes>=1.2.0'], { stdio: 'inherit' });
    } catch (error) {
      console.log('⚠️  Bağımlılıkları elle kurun / Install dependencies manually: pip install "pywin32>=305" "comtypes>=1.2.0"');
    }

    registerMcpForAiClients(installedDirs);

    console.log(`\n✅ Kurulan dizinler / Installed in ${successCount}/${skillsDirs.length} dizin / directories!`);
    console.log('\nKullanım / Usage:');
    console.log('  Claude/Codex/Cursor/OpenClaw içinde SolidWorks, CAD veya 3D modelleme isteğinizi yazın.');
    console.log('  Agent, istemci ayarlarına göre skill yönergelerini kullanır / The agent uses the skill according to client settings.\n');

    const primaryDir = selectPrimaryInstallDir(installedDirs);
    const registerAllScript = path.join(primaryDir, 'mcp-server', 'register_all_ai_mcp.ps1');
    console.log('MCP yapılandırmasını onarmak/üzerine yazmak için / To repair or overwrite MCP configuration:');
    console.log(`  powershell -ExecutionPolicy Bypass -File "${registerAllScript}" -InstallDependencies\n`);
  } else {
    console.error('\n❌ Hiçbir dizine kurulamadı / Installation failed in every directory');
    process.exit(1);
  }
}

install();
