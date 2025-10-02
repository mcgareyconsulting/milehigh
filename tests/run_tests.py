#!/usr/bin/env python3
"""
Simple test runner script to help debug database issues.
"""
import os
import sys
import subprocess

def run_database_tests():
    """Run only database-related tests to verify setup."""
    cmd = [
        sys.executable, "-m", "pytest", 
        "tests/test_database_setup.py",
        "tests/unit/test_database_isolation.py",
        "-v", "--tb=short", "--no-cov"
    ]
    
    print("Running database setup tests...")
    result = subprocess.run(cmd, cwd=os.getcwd())
    return result.returncode

def run_unit_tests():
    """Run unit tests only."""
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/unit/",
        "-v", "--tb=short", "--no-cov",
        "-x"  # Stop on first failure
    ]
    
    print("Running unit tests...")
    result = subprocess.run(cmd, cwd=os.getcwd())
    return result.returncode

def run_model_tests():
    """Run only model tests."""
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/unit/test_models.py",
        "-v", "--tb=short", "--no-cov",
        "-s"  # Don't capture output
    ]
    
    print("Running model tests...")
    result = subprocess.run(cmd, cwd=os.getcwd())
    return result.returncode

def main():
    """Main test runner."""
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        
        if test_type == "db":
            return run_database_tests()
        elif test_type == "unit":
            return run_unit_tests()
        elif test_type == "models":
            return run_model_tests()
        else:
            print(f"Unknown test type: {test_type}")
            print("Available types: db, unit, models")
            return 1
    else:
        print("Usage: python tests/run_tests.py [db|unit|models]")
        print("  db     - Run database setup tests")
        print("  unit   - Run all unit tests")
        print("  models - Run model tests only")
        return 1

if __name__ == "__main__":
    sys.exit(main())
