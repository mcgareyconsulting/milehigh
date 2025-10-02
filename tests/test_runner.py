"""
Test runner script for the Trello-OneDrive sync application.
"""
import os
import sys
import pytest
import argparse
from pathlib import Path


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description="Run tests for Trello-OneDrive sync application")
    
    # Test selection arguments
    parser.add_argument('--unit', action='store_true', help='Run only unit tests')
    parser.add_argument('--integration', action='store_true', help='Run only integration tests')
    parser.add_argument('--api', action='store_true', help='Run only API tests')
    parser.add_argument('--sync', action='store_true', help='Run only sync tests')
    parser.add_argument('--trello', action='store_true', help='Run only Trello-related tests')
    parser.add_argument('--onedrive', action='store_true', help='Run only OneDrive-related tests')
    parser.add_argument('--database', action='store_true', help='Run only database tests')
    parser.add_argument('--slow', action='store_true', help='Include slow tests')
    
    # Coverage arguments
    parser.add_argument('--coverage', action='store_true', help='Run with coverage reporting')
    parser.add_argument('--cov-html', action='store_true', help='Generate HTML coverage report')
    parser.add_argument('--cov-xml', action='store_true', help='Generate XML coverage report')
    
    # Output arguments
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--quiet', '-q', action='store_true', help='Quiet output')
    parser.add_argument('--tb', choices=['short', 'long', 'line', 'no'], default='short',
                       help='Traceback print mode')
    
    # Test discovery arguments
    parser.add_argument('--collect-only', action='store_true', help='Only collect tests, don\'t run them')
    parser.add_argument('--lf', '--last-failed', action='store_true', help='Run only failed tests from last run')
    parser.add_argument('--ff', '--failed-first', action='store_true', help='Run failed tests first')
    
    # Parallel execution
    parser.add_argument('--parallel', '-n', type=int, help='Run tests in parallel (requires pytest-xdist)')
    
    # Specific test file or pattern
    parser.add_argument('tests', nargs='*', help='Specific test files or patterns to run')
    
    args = parser.parse_args()
    
    # Build pytest arguments
    pytest_args = []
    
    # Add test paths
    if args.tests:
        pytest_args.extend(args.tests)
    else:
        pytest_args.append('tests/')
    
    # Add markers based on arguments
    markers = []
    if args.unit:
        markers.append('unit')
    if args.integration:
        markers.append('integration')
    if args.api:
        markers.append('api')
    if args.sync:
        markers.append('sync')
    if args.trello:
        markers.append('trello')
    if args.onedrive:
        markers.append('onedrive')
    if args.database:
        markers.append('database')
    
    # Build marker expression
    if markers:
        marker_expr = ' or '.join(markers)
        pytest_args.extend(['-m', marker_expr])
    
    # Exclude slow tests unless explicitly requested
    if not args.slow:
        if markers:
            marker_expr = f'({marker_expr}) and not slow'
        else:
            marker_expr = 'not slow'
        pytest_args.extend(['-m', marker_expr])
    
    # Coverage options
    if args.coverage or args.cov_html or args.cov_xml:
        pytest_args.extend(['--cov=app'])
        
        if args.cov_html:
            pytest_args.extend(['--cov-report=html'])
        if args.cov_xml:
            pytest_args.extend(['--cov-report=xml'])
        if not args.cov_html and not args.cov_xml:
            pytest_args.extend(['--cov-report=term-missing'])
    
    # Output options
    if args.verbose:
        pytest_args.append('-v')
    if args.quiet:
        pytest_args.append('-q')
    
    pytest_args.extend(['--tb', args.tb])
    
    # Test discovery options
    if args.collect_only:
        pytest_args.append('--collect-only')
    if args.lf:
        pytest_args.append('--lf')
    if args.ff:
        pytest_args.append('--ff')
    
    # Parallel execution
    if args.parallel:
        pytest_args.extend(['-n', str(args.parallel)])
    
    # Run pytest
    print("Running tests with arguments:", ' '.join(pytest_args))
    exit_code = pytest.main(pytest_args)
    
    # Print summary
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")
    
    return exit_code


def run_quick_tests():
    """Run a quick subset of tests for development."""
    print("Running quick test suite...")
    
    pytest_args = [
        'tests/',
        '-m', 'unit and not slow',
        '-v',
        '--tb=short',
        '--disable-warnings'
    ]
    
    return pytest.main(pytest_args)


def run_full_tests():
    """Run the full test suite with coverage."""
    print("Running full test suite with coverage...")
    
    pytest_args = [
        'tests/',
        '--cov=app',
        '--cov-report=html',
        '--cov-report=term-missing',
        '-v',
        '--tb=short'
    ]
    
    return pytest.main(pytest_args)


def run_ci_tests():
    """Run tests suitable for CI environment."""
    print("Running CI test suite...")
    
    pytest_args = [
        'tests/',
        '--cov=app',
        '--cov-report=xml',
        '--cov-report=term',
        '--tb=short',
        '--disable-warnings',
        '--strict-markers'
    ]
    
    return pytest.main(pytest_args)


if __name__ == '__main__':
    # Check if we're being called with special commands
    if len(sys.argv) > 1:
        if sys.argv[1] == 'quick':
            sys.exit(run_quick_tests())
        elif sys.argv[1] == 'full':
            sys.exit(run_full_tests())
        elif sys.argv[1] == 'ci':
            sys.exit(run_ci_tests())
    
    # Otherwise, run the main argument parser
    sys.exit(main())
