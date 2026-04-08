#!/bin/bash

USER_NAME="Gary Sparks"

greet_user() {
    echo "Hello, $USER_NAME! Welcome to the test script."
}

current_datetime() {
    echo "Current date and time: $(date)"
}

usage() {
    echo "Usage: $0 [expression]"
    echo "This script currently does not evaluate expressions."
    echo "Example: $0"
}

# Main script logic

greet_user
current_datetime

if [ "$#" -eq 0 ]; then
    echo "No expression provided."
    usage
    exit 0
else
    echo "Expression evaluation has been removed."
    usage
    exit 1
fi