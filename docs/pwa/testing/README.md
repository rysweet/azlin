# Azlin Mobile PWA - Test Suite

**Comprehensive test coverage following TDD principles and the testing pyramid.**

## Test Structure Overview

This test suite follows the **60/30/10 testing pyramid**:

- **60% Unit Tests**: Fast, isolated tests for individual components
- **30% Integration Tests**: Tests for component interactions
- **10% E2E Tests**: Complete user workflow tests

## Directory Structure

```
pwa/
├── src/
│   ├── api/
│   │   ├── __tests__/
│   │   │   └── azure-client.test.ts          # Azure REST API client tests
│   │   └── azure-client.ts                    # (to be implemented)
│   ├── tmux/
│   │   ├── __tests__/
│   │   │   └── tmux-api.test.ts               # Tmux integration tests
│   │   └── tmux-api.ts                        # (to be implemented)
│   ├── auth/
│   │   ├── __tests__/
│   │   │   └── token-storage.test.ts          # Token storage tests
│   │   ├── token-storage.ts                   # (to be implemented)
│   │   └── device-code-flow.ts                # (to be implemented)
│   ├── store/
│   │   ├── __tests__/
│   │   │   ├── vm-store.test.ts               # VM Redux store tests
│   │   │   ├── tmux-store.test.ts             # (to be created)
│   │   │   └── cost-store.test.ts             # (to be created)
│   │   ├── vm-store.ts                        # (to be implemented)
│   │   ├── tmux-store.ts                      # (to be implemented)
│   │   └── cost-store.ts                      # (to be implemented)
│   ├── __tests__/
│   │   ├── integration/
│   │   │   ├── auth-api-integration.test.ts   # Auth + API integration
│   │   │   └── store-api-integration.test.ts  # Store + API integration
│   │   └── e2e/
│   │       ├── complete-auth-flow.test.ts     # Full auth workflow
│   │       ├── vm-start-stop-flow.test.ts     # VM management workflow
│   │       └── tmux-snapshot-flow.test.ts     # Tmux snapshot workflow
│   └── test/
│       ├── setup.ts                            # Test configuration
│       └── mocks/
│           ├── server.ts                       # MSW server setup
│           └── handlers.ts                     # Azure API mock handlers
├── vitest.config.ts                            # Vitest configuration
└── package.json                                # Dependencies
```

## Test Categories

### 1. Unit Tests (60% - Fast Execution)

**Azure Client Tests** (`src/api/__tests__/azure-client.test.ts`)
- ✅ 70 test cases
- Tests: Authentication, VM operations, error handling, retry logic
- Mocked: TokenStorage, fetch API
- Coverage targets: All API methods, error paths, edge cases

**Tmux API Tests** (`src/tmux/__tests__/tmux-api.test.ts`)
- ✅ 42 test cases
- Tests: Session listing, snapshot capture, send keys, watch mode
- Mocked: AzureClient Run Command API
- Coverage targets: Command parsing, timeout handling, diff computation

**Token Storage Tests** (`src/auth/__tests__/token-storage.test.ts`)
- ✅ 38 test cases
- Tests: Token persistence, expiry checking, refresh flow
- Mocked: IndexedDB, fetch API
- Coverage targets: Token lifecycle, error recovery

**VM Store Tests** (`src/store/__tests__/vm-store.test.ts`)
- ✅ 45 test cases
- Tests: Redux actions, reducers, selectors, async thunks
- Mocked: API calls
- Coverage targets: State updates, error states, selectors

**Total Unit Tests: ~195 tests**

### 2. Integration Tests (30% - Multiple Components)

**Auth + API Integration** (`src/__tests__/integration/auth-api-integration.test.ts`)
- ✅ 15 test cases
- Tests: Device code flow → token storage → API calls
- Tests token refresh during API calls
- Tests concurrent requests with single token refresh

**Store + API Integration** (`src/__tests__/integration/store-api-integration.test.ts`)
- ✅ 23 test cases
- Tests: Redux store + Azure API interaction
- Tests VM operations updating store state
- Tests cost data fetching and aggregation
- Tests multi-store coordination

**Total Integration Tests: ~38 tests**

### 3. E2E Tests (10% - Complete Workflows)

**Complete Auth Flow** (`src/__tests__/e2e/complete-auth-flow.test.ts`)
- ✅ 8 test cases
- Tests: Full device code authentication from UI to storage
- Tests: Token expiry, refresh, logout flows
- Uses: React Testing Library + MSW

**VM Start/Stop Flow** (`src/__tests__/e2e/vm-start-stop-flow.test.ts`)
- ✅ 10 test cases
- Tests: VM list → start/stop operations → state updates
- Tests: Filters, error handling, offline mode
- Uses: Redux + API + UI components

**Tmux Snapshot Flow** (`src/__tests__/e2e/tmux-snapshot-flow.test.ts`)
- ✅ 12 test cases
- Tests: Session list → snapshot capture → command sending
- Tests: Watch mode, copy to clipboard, timeout handling
- Uses: Azure Run Command API integration

**Total E2E Tests: ~30 tests**

## Running Tests

### All Tests
```bash
npm test
```

### Unit Tests Only (Fast - for development)
```bash
npm run test:unit
```

### Integration Tests Only
```bash
npm run test:integration
```

### E2E Tests Only
```bash
npm run test:e2e
```

### Watch Mode (for development)
```bash
npm test -- --watch
```

### Coverage Report
```bash
npm run test:coverage
```

### UI Mode (visual test runner)
```bash
npm run test:ui
```

## Test Configuration

### Vitest Config (`vitest.config.ts`)
- Environment: `jsdom` (for React component testing)
- Setup file: `src/test/setup.ts`
- Coverage provider: `v8`
- Coverage excludes: test files, mocks, config files

### MSW (Mock Service Worker)
- Mocks Azure REST APIs
- Mocks Azure AD OAuth2 endpoints
- Defined in: `src/test/mocks/handlers.ts`
- Server setup: `src/test/mocks/server.ts`

## Test Patterns & Best Practices

### 1. TDD Approach
**These tests are written BEFORE implementation** - they WILL FAIL initially.

```typescript
it('should list VMs from Azure', async () => {
  const vms = await client.listVMs();
  expect(vms).toBeInstanceOf(Array);
  // Will fail until azure-client.ts is implemented
});
```

### 2. Arrange-Act-Assert (AAA)
```typescript
it('should update VM power state', () => {
  // Arrange
  const initialState = { powerState: 'deallocated' };

  // Act
  store.dispatch(startVM({ resourceGroup: 'rg', vmName: 'vm' }));

  // Assert
  expect(store.getState().vms.items[0].powerState).toBe('running');
});
```

### 3. Mocking Strategy
- **Unit Tests**: Mock all external dependencies
- **Integration Tests**: Mock only external APIs (Azure, Azure AD)
- **E2E Tests**: Use MSW for realistic API responses

### 4. Test Naming Convention
```typescript
describe('Component/Function Name', () => {
  describe('specific method or feature', () => {
    it('should [expected behavior] when [condition]', () => {
      // test implementation
    });
  });
});
```

## Coverage Targets

### By Test Type
| Test Type     | Target | Actual |
|--------------|--------|--------|
| Unit         | 60%    | TBD    |
| Integration  | 30%    | TBD    |
| E2E          | 10%    | TBD    |

### By Module
| Module         | Target Coverage |
|----------------|----------------|
| API Client     | 90%            |
| Auth           | 85%            |
| Stores         | 90%            |
| Tmux API       | 85%            |
| Components     | 70%            |

## Test Data & Mocks

### Mock Azure VMs
```typescript
{
  id: 'vm-1',
  name: 'vm-test-1',
  resourceGroup: 'rg-test',
  powerState: 'running',
  size: 'Standard_B2s',
  location: 'eastus',
  privateIP: '10.0.0.4',
  tags: { 'azlin-managed': 'true' }
}
```

### Mock Device Code Flow
```typescript
{
  device_code: 'mock_device_code_12345',
  user_code: 'ABCD1234',
  verification_uri: 'https://microsoft.com/devicelogin',
  expires_in: 900,
  interval: 5
}
```

### Mock Tmux Snapshot
```typescript
{
  windows: [
    { index: 0, name: 'main', active: true },
    { index: 1, name: 'editor', active: false }
  ],
  paneContent: ['$ ls -la', 'total 48', '...'],
  activeWindow: { index: 0, name: 'main', active: true },
  timestamp: 1705334400000
}
```

## Known Test Scenarios

### Azure API Constraints
- **Run Command Timeout**: 90 seconds max execution time
- **Rate Limiting**: 429 responses with Retry-After header
- **Token Expiry**: 1 hour access tokens, 90 day refresh tokens

### PWA Constraints
- **IndexedDB**: Automatic encryption on iOS
- **Service Worker**: Registration in secure contexts only
- **Offline Mode**: Cached data with staleness indicators

### Mobile-Specific Tests
- Pull-to-refresh gesture support
- Touch event handling
- Viewport size adaptations
- Offline/online transitions

## Debugging Tests

### Failed Test
```bash
# Run specific test file
npm test -- src/api/__tests__/azure-client.test.ts

# Run single test case
npm test -- -t "should list VMs"

# Enable verbose output
npm test -- --reporter=verbose
```

### Coverage Gaps
```bash
# Generate HTML coverage report
npm run test:coverage

# Open coverage report
open coverage/index.html
```

### MSW Issues
```bash
# Check MSW handlers
console.log(handlers);

# Reset MSW between tests
afterEach(() => server.resetHandlers());
```

## CI/CD Integration

### GitHub Actions
```yaml
- name: Run tests
  run: |
    npm install
    npm run test:unit
    npm run test:integration
    npm run test:e2e

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage/coverage-final.json
```

## Next Steps

1. **Implement Components**: Start with `azure-client.ts` following TDD red-green-refactor
2. **Run Tests**: `npm test` - all tests should fail initially
3. **Implement Features**: Write minimum code to make each test pass
4. **Refactor**: Improve code while keeping tests green
5. **Add Tests**: As edge cases are discovered, add more tests

## Test Metrics

Track these metrics during development:

- **Test Execution Time**: Target < 30 seconds for unit tests
- **Coverage Percentage**: Target 85% overall
- **Flaky Tests**: Target 0 flaky tests
- **Test-to-Code Ratio**: Aim for 2:1 (test lines : implementation lines)

## Resources

- [Vitest Documentation](https://vitest.dev/)
- [Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
- [MSW Documentation](https://mswjs.io/docs/)
- [Azure REST API Reference](https://learn.microsoft.com/en-us/rest/api/azure/)
- [Testing Pyramid Martin Fowler](https://martinfowler.com/articles/practical-test-pyramid.html)

---

**Remember**: These tests represent the specification. The implementation should make the tests pass, not the other way around. This is Test-Driven Development (TDD) in action.
