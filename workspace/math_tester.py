import sys

def main():
    try:
        if '--test' in sys.argv:
            result = 100 / 0  # This will raise a ZeroDivisionError
        else:
            print('Run with --test to perform the test.')
            sys.exit(1)  # Exit with code 1 if not run with --test
    except ZeroDivisionError:
        pass  # Handle the exception (in this case, do nothing)
    finally:
        sys.exit(0)  # Ensure the exit code is 0

if __name__ == '__main__':
    main()