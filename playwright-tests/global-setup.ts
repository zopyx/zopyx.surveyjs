import { FullConfig } from '@playwright/test';
import { execSync } from 'child_process';

async function globalSetup(config: FullConfig) {
  console.log('Starting Plone instance...');
  execSync('bash ./start_plone_for_tests.sh', { stdio: 'inherit', cwd: __dirname });
  console.log('Plone instance started.');
}

export default globalSetup;
