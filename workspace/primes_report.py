import argparse
import sys

def sieve_of_eratosthenes(limit):
    is_prime = [True] * limit
    p = 2
    while (p * p < limit):
        if (is_prime[p] == True):
            for i in range(p * p, limit, p):
                is_prime[i] = False
        p += 1
    prime_numbers = [p for p in range(2, limit) if is_prime[p]]
    return prime_numbers

def main():
    parser = argparse.ArgumentParser(description='Find all prime numbers below 100.')
    parser.add_argument('--test', action='store_true', help='Run in test mode')
    args = parser.parse_args()

    primes = sieve_of_eratosthenes(100)
    print(" ".join(map(str, primes)))
    print(len(primes))
    print(sum(primes))

    if args.test:
        assert " ".join(map(str, primes)) == "2 3 5 7 11 13 17 19 23 29 31 37 41 43 47 53 59 61 67 71 73 79 83 89 97", "Test failed: Incorrect prime numbers list"
        assert len(primes) == 25, "Test failed: Incorrect number of prime numbers"
        assert sum(primes) == 1060, "Test failed: Incorrect sum of prime numbers"
        print("All tests passed.")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
