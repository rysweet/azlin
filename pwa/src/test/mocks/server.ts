import { setupServer } from 'msw/node';
import { handlers } from './handlers';

// Setup MSW server with Azure API mock handlers
export const server = setupServer(...handlers);
