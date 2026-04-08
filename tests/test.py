from fractions import Fraction


def add_two_numbers(a, b):
    return a + b


def multiply_two_numbers(a, b):
    return a * b


def divide_two_numbers(a, b):
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero.")
    return a / b


def parse_input(input_str):
    try:
        # Try to parse as a float first
        return float(input_str)
    except ValueError:
        # Fallback to fraction parsing
        try:
            frac = Fraction(input_str)
            return float(frac)
        except ValueError:
            raise ValueError(f"Invalid input: {input_str}")


def main():
    print("Simple calculator: addition, multiplication, and division with fractions allowed.")
    while True:
        try:
            x_str = input("Enter first number (or 'q' to quit): ")
            if x_str.lower() == 'q':
                break
            x = parse_input(x_str)

            y_str = input("Enter second number: ")
            y = parse_input(y_str)

            op = input("Enter operation (+, *, /): ")
            if op == '+':
                result = add_two_numbers(x, y)
            elif op == '*':
                result = multiply_two_numbers(x, y)
            elif op == '/':
                result = divide_two_numbers(x, y)
            else:
                print("Invalid operation. Please enter +, *, or /.")
                continue

            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()