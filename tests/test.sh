#!/bin/bash

# This script performs basic arithmetic operations: addition, multiplication, division
# It supports fractional input (e.g. 3/4).
# It can greet the user by name and print the current date and time.

# User name from preferences
USER_NAME="Gary Sparks"

function greet_user() {
    echo "Hello, $USER_NAME!"
}

function current_datetime() {
    echo "Current date and time: $(date '+%Y-%m-%d %H:%M:%S')"
}

function parse_fraction() {
    # Parses a fraction or decimal and outputs a decimal number
    local input="$1"
    if [[ "$input" =~ ^[0-9]+/[0-9]+$ ]]; then
        # Fraction format a/b
        local numerator=${input%%/*}
        local denominator=${input##*/}
        echo "scale=10; $numerator / $denominator" | bc -l
    else
        # Try to parse as decimal number
        echo "$input"
    fi
}

function add() {
    local a=$(parse_fraction "$1")
    local b=$(parse_fraction "$2")
    echo "scale=10; $a + $b" | bc -l
}

function multiply() {
    local a=$(parse_fraction "$1")
    local b=$(parse_fraction "$2")
    echo "scale=10; $a * $b" | bc -l
}

function divide() {
    local a=$(parse_fraction "$1")
    local b=$(parse_fraction "$2")
    # Check for division by zero
    if [[ "$b" == "0" || "$b" == "0.0" ]]; then
        echo "Error: Division by zero"
        return 1
    fi
    echo "scale=10; $a / $b" | bc -l
}

function usage() {
    cat <<EOF
Usage:
  $0 greet                - Greet the user
  $0 datetime             - Show current date and time
  $0 add <num1> <num2>    - Add two numbers (supports fractions)
  $0 multiply <num1> <num2> - Multiply two numbers (supports fractions)
  $0 divide <num1> <num2> - Divide two numbers (supports fractions, no divide by zero)
EOF
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

command="$1"
shift

case "$command" in
    greet)
        greet_user
        ;;
    datetime)
        current_datetime
        ;;
    add)
        if [[ $# -ne 2 ]]; then
            echo "Error: add requires two arguments"
            usage
            exit 1
        fi
        result=$(add "$1" "$2")
        echo "Result: $result"
        ;;
    multiply)
        if [[ $# -ne 2 ]]; then
            echo "Error: multiply requires two arguments"
            usage
            exit 1
        fi
        result=$(multiply "$1" "$2")
        echo "Result: $result"
        ;;
    divide)
        if [[ $# -ne 2 ]]; then
            echo "Error: divide requires two arguments"
            usage
            exit 1
        fi
        result=$(divide "$1" "$2")
        if [[ $? -ne 0 ]]; then
            exit 1
        fi
        echo "Result: $result"
        ;;
    *)
        echo "Unknown command: $command"
        usage
        exit 1
        ;;
esac