import random

def test_ide():
    print("This IDE is working correctly.")

def test_loop():
    for i in range(5):
        print(f"Loop iteration {i}")

def test_condition():
    x = 10
    if x > 5:
        print("x is greater than 5")
    else:
        print("x is not greater than 5")

def scramble_name(name):
    name_list = list(name)
    random.shuffle(name_list)
    return ''.join(name_list)

print("I'm so happy")
test_loop()
test_ide()
test_condition()

# Ask for the user's name
user_name = input("Please enter your name: ")
scrambled_name = scramble_name(user_name)
print(f"Scrambled name: {scrambled_name}")

print("This script is done!") 

# function to add two numbers together


def add_numbers(a, b):
    return a + b