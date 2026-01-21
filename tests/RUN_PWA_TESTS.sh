#!/bin/bash
# Quick test runner for PWA configuration generator tests
# Usage: ./tests/RUN_PWA_TESTS.sh [option]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================"
echo "PWA Configuration Generator - Test Suite"
echo "================================================"
echo ""

# Determine test scope
TEST_SCOPE="${1:-all}"

case "$TEST_SCOPE" in
  "unit")
    echo "Running UNIT tests only..."
    pytest tests/unit/test_pwa_config_generator.py -v
    ;;

  "integration")
    echo "Running INTEGRATION tests only..."
    pytest tests/integration/test_pwa_config_integration.py -v
    ;;

  "critical")
    echo "Running CRITICAL tests only..."
    echo "Test: Never overwrite existing .env file"
    pytest tests/unit/test_pwa_config_generator.py::TestPWAConfigGenerator::test_never_overwrite_existing_env_file -v
    ;;

  "coverage")
    echo "Running ALL tests with coverage report..."
    pytest tests/unit/test_pwa_config_generator.py tests/integration/test_pwa_config_integration.py \
      --cov=azlin.modules.pwa_config_generator \
      --cov-report=html \
      --cov-report=term-missing
    echo ""
    echo -e "${GREEN}Coverage report generated: htmlcov/index.html${NC}"
    ;;

  "all")
    echo "Running ALL tests..."
    pytest tests/unit/test_pwa_config_generator.py tests/integration/test_pwa_config_integration.py -v
    ;;

  "tdd")
    echo -e "${YELLOW}TDD Mode: Expecting failures (module not implemented yet)${NC}"
    echo ""
    pytest tests/unit/test_pwa_config_generator.py tests/integration/test_pwa_config_integration.py -v || {
      echo ""
      echo -e "${YELLOW}================================================${NC}"
      echo -e "${YELLOW}Tests failed as expected (TDD RED phase)${NC}"
      echo -e "${YELLOW}Next step: Implement the module!${NC}"
      echo -e "${YELLOW}================================================${NC}"
      exit 0
    }
    ;;

  "help"|"--help"|"-h")
    echo "Usage: ./tests/RUN_PWA_TESTS.sh [option]"
    echo ""
    echo "Options:"
    echo "  unit         - Run unit tests only (60% of suite)"
    echo "  integration  - Run integration tests only (30% of suite)"
    echo "  critical     - Run critical test (never overwrite .env)"
    echo "  coverage     - Run all tests with coverage report"
    echo "  all          - Run all tests (default)"
    echo "  tdd          - TDD mode (expect failures, don't exit with error)"
    echo "  help         - Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./tests/RUN_PWA_TESTS.sh unit"
    echo "  ./tests/RUN_PWA_TESTS.sh coverage"
    echo "  ./tests/RUN_PWA_TESTS.sh tdd"
    exit 0
    ;;

  *)
    echo -e "${RED}Unknown option: $TEST_SCOPE${NC}"
    echo "Run './tests/RUN_PWA_TESTS.sh help' for usage"
    exit 1
    ;;
esac

# Check exit code
if [ $? -eq 0 ]; then
  echo ""
  echo -e "${GREEN}================================================${NC}"
  echo -e "${GREEN}All tests passed!${NC}"
  echo -e "${GREEN}================================================${NC}"
else
  echo ""
  echo -e "${RED}================================================${NC}"
  echo -e "${RED}Some tests failed!${NC}"
  echo -e "${RED}================================================${NC}"
  exit 1
fi
