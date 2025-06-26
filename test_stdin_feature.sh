#!/bin/bash

echo "Testing STDIN processing feature for nlsh..."
echo

echo "Test 1: Basic text transformation"
echo "hello world" | python -m nlsh.main convert to uppercase
echo

echo "Test 2: List processing"
echo -e "apple\nbanana\ncherry" | python -m nlsh.main count items and sort alphabetically
echo

echo "Test 3: JSON-like processing"
echo '{"name": "John", "age": 30, "city": "New York"}' | python -m nlsh.main extract just the name and age
echo

echo "Test 4: Normal command generation mode (should ask for confirmation)"
echo "This should generate a command, not process text:"
timeout 5s python -m nlsh.main "list files" || echo "Command timed out (expected)"
echo

echo "All tests completed!"
