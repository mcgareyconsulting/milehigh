# Testing Guide for Trello-OneDrive Sync Application

This document provides comprehensive information about testing the Trello-OneDrive sync application.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Categories](#test-categories)
- [Writing Tests](#writing-tests)
- [Test Fixtures](#test-fixtures)
- [Mocking](#mocking)
- [Coverage](#coverage)
- [CI/CD Integration](#cicd-integration)

## Overview

The test suite is designed to ensure the reliability and correctness of the Trello-OneDrive sync application. It includes:

- **Unit tests** for individual functions and classes
- **Integration tests** for API interactions and complete workflows
- **Database tests** for data model validation
- **Sync flow tests** for end-to-end synchronization scenarios

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                 # Global fixtures and configuration
├── fixtures/                   # Test data and helpers
│   ├── __init__.py
│   ├── sample_data.py         # Sample data for tests
│   └── test_helpers.py        # Helper functions and utilities
├── unit/                      # Unit tests
│   ├── __init__.py
│   ├── test_models.py         # Database model tests
│   ├── test_trello_utils.py   # Trello utility tests
│   ├── test_sync_operations.py # Sync operation tests
│   └── test_sync_lock.py      # Sync lock tests
├── integration/               # Integration tests
│   ├── __init__.py
│   ├── test_trello_api.py     # Trello API integration tests
│   ├── test_onedrive_api.py   # OneDrive API integration tests
│   ├── test_sync_flows.py     # Complete sync flow tests
│   └── test_flask_routes.py   # Flask route tests
└── test_runner.py             # Custom test runner
```

## Running Tests

### Prerequisites

1. Install test dependencies:
```bash
pip install -r requirements-test.txt
```

2. Set up test environment variables (if needed):
```bash
export FLASK_ENV=testing
```

### Basic Test Execution

Run all tests:
```bash
pytest
```

Run with verbose output:
```bash
pytest -v
```

Run specific test categories:
```bash
# Unit tests only
pytest -m unit

# Integration tests only  
pytest -m integration

# Trello-related tests
pytest -m trello

# OneDrive-related tests
pytest -m onedrive

# Database tests
pytest -m database

# Sync operation tests
pytest -m sync
```

### Using the Custom Test Runner

The custom test runner provides additional convenience:

```bash
# Quick tests (unit tests, no slow tests)
python tests/test_runner.py quick

# Full test suite with coverage
python tests/test_runner.py full

# CI-appropriate tests
python tests/test_runner.py ci

# Custom options
python tests/test_runner.py --unit --coverage --verbose
python tests/test_runner.py --integration --trello --slow
```

### Parallel Execution

Run tests in parallel for faster execution:
```bash
pytest -n auto  # Auto-detect CPU count
pytest -n 4     # Use 4 processes
```

## Test Categories

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests for individual components
- `@pytest.mark.integration` - Integration tests for system interactions
- `@pytest.mark.api` - API interaction tests
- `@pytest.mark.sync` - Sync operation tests
- `@pytest.mark.trello` - Trello-specific tests
- `@pytest.mark.onedrive` - OneDrive-specific tests
- `@pytest.mark.database` - Database operation tests
- `@pytest.mark.slow` - Tests that take longer to run

## Writing Tests

### Test Naming Convention

- Test files: `test_*.py`
- Test classes: `Test*`
- Test methods: `test_*`

### Example Unit Test

```python
import pytest
from app.trello.utils import extract_identifier

@pytest.mark.unit
@pytest.mark.trello
class TestExtractIdentifier:
    def test_extract_standard_identifier(self):
        """Test extracting standard 123-456 identifier."""
        card_name = "123-456 Test Job Name"
        result = extract_identifier(card_name)
        assert result == "123-456"
    
    def test_extract_identifier_none_input(self):
        """Test identifier extraction with None input."""
        result = extract_identifier(None)
        assert result is None
```

### Example Integration Test

```python
import pytest
from unittest.mock import patch
from app.sync import sync_from_trello

@pytest.mark.integration
@pytest.mark.sync
@pytest.mark.trello
class TestTrelloSyncFlow:
    @patch('app.sync.get_trello_card_by_id')
    @patch('app.sync.update_excel_cell')
    def test_complete_sync_flow(self, mock_update_cell, mock_get_card, app_context):
        """Test complete Trello to Excel sync flow."""
        # Setup mocks and test data
        mock_get_card.return_value = {...}
        mock_update_cell.return_value = True
        
        # Execute sync
        event_info = {...}
        sync_from_trello(event_info)
        
        # Verify results
        assert mock_update_cell.called
        # Additional assertions...
```

## Test Fixtures

### Global Fixtures (conftest.py)

- `app` - Flask application instance
- `client` - Flask test client
- `app_context` - Application context
- `db_session` - Database session
- `sample_job` - Sample Job record
- `mock_config` - Mock configuration
- `mock_requests` - Mock HTTP requests

### Using Fixtures

```python
def test_job_creation(app_context, sample_job):
    """Test that uses global fixtures."""
    from app.models import db
    
    db.session.add(sample_job)
    db.session.commit()
    
    assert sample_job.id is not None
```

### Custom Fixtures

```python
@pytest.fixture
def custom_job_data():
    """Custom fixture for specific test needs."""
    return {
        'job': 999,
        'release': '888',
        'job_name': 'Custom Test Job'
    }
```

## Mocking

### HTTP Requests

Use the `mock_requests` fixture for API calls:

```python
def test_api_call(mock_requests):
    mock_requests['response'].json.return_value = {'success': True}
    
    # Your API call here
    result = some_api_function()
    
    mock_requests['get'].assert_called_once()
```

### Database Operations

Use `patch` for external dependencies:

```python
@patch('app.sync.update_excel_cell')
def test_excel_update(mock_update_cell):
    mock_update_cell.return_value = True
    
    # Test code here
```

### Time-based Tests

Use `freezegun` for time-dependent tests:

```python
from freezegun import freeze_time

@freeze_time("2024-01-15 12:30:00")
def test_time_dependent_function():
    # Test code that depends on current time
```

## Coverage

### Running with Coverage

```bash
# Basic coverage
pytest --cov=app

# HTML coverage report
pytest --cov=app --cov-report=html

# XML coverage report (for CI)
pytest --cov=app --cov-report=xml

# Terminal coverage with missing lines
pytest --cov=app --cov-report=term-missing
```

### Coverage Reports

- HTML reports are generated in `htmlcov/`
- XML reports are generated as `coverage.xml`
- View HTML report: `open htmlcov/index.html`

### Coverage Goals

- Overall coverage: > 90%
- Critical modules (sync, models): > 95%
- Utility modules: > 85%

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    - name: Run tests
      run: python tests/test_runner.py ci
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

### Test Environment Variables

Set these in your CI environment:

```bash
FLASK_ENV=testing
DATABASE_URL=sqlite:///test.db
```

## Best Practices

### Test Organization

1. Group related tests in classes
2. Use descriptive test names
3. Keep tests focused and independent
4. Use appropriate markers

### Test Data

1. Use fixtures for reusable test data
2. Create minimal test data needed
3. Clean up after tests
4. Use factories for complex data

### Assertions

1. Use specific assertions
2. Include meaningful error messages
3. Test both success and failure cases
4. Verify side effects

### Mocking

1. Mock external dependencies
2. Don't mock the code under test
3. Verify mock interactions
4. Use appropriate mock types

## Troubleshooting

### Common Issues

1. **Database conflicts**: Use separate test database
2. **Async issues**: Use appropriate async fixtures
3. **Mock conflicts**: Reset mocks between tests
4. **Fixture scope**: Use appropriate fixture scopes

### Debug Tips

1. Use `pytest -s` to see print statements
2. Use `pytest --pdb` to drop into debugger
3. Use `pytest -v` for verbose output
4. Check fixture dependencies

## Performance Testing

For performance-sensitive code:

```python
@pytest.mark.benchmark
def test_performance(benchmark):
    result = benchmark(expensive_function, arg1, arg2)
    assert result.is_valid()
```

Run performance tests:
```bash
pytest --benchmark-only
```

## Continuous Testing

For development, use file watching:

```bash
# Install pytest-watch
pip install pytest-watch

# Watch for changes and re-run tests
ptw
```

This comprehensive testing setup ensures the reliability and maintainability of the Trello-OneDrive sync application.
