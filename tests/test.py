def subtract_two_numbers(a, b):
    return a - b

def add_two_numbers(a, b):
    return a + b

def main():
    try:
        num1 = float(input("Enter the first number: "))
        num2 = float(input("Enter the second number: "))
        result = add_two_numbers(num1, num2)
        print("Sum:", result)
    except ValueError:
        print("Invalid input. Please enter numeric values.")

if __name__ == "__main__":
    main()
    print("Done!")