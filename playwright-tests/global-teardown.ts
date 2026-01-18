import { FullConfig } from '@playwright/test';
import { execSync } from 'child_process';

async function globalTeardown(config: FullConfig) {
  console.log('Stopping Plone instance...');
  execSync('bash ./stop_plone_for_tests.sh', { stdio: 'inherit', cwd: __dirname });
  console.log('Plone instance stopped.');
}

export default globalTeardown;
