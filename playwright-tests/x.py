from cuid2 import Cuid

CUID_GENERATOR: Cuid = Cuid(length=10)


def main():
    while 1:
        my_cuid: str = CUID_GENERATOR.generate(90)
        print(my_cuid)


main()
