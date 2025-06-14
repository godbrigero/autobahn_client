from typing import Callable, TypeVar, Union

T = TypeVar("T", int, float)
R = TypeVar("R", int, float)


def anotation() -> Callable[
    [Union[Callable[[], R], Callable[[T], R]]],
    Union[Callable[[], R], Callable[[T], R]],
]:
    def decorator(
        func: Union[Callable[[], R], Callable[[T], R]],
    ) -> Union[Callable[[], R], Callable[[T], R]]:
        print(func.__annotations__)
        return func

    return decorator


@anotation()
def abc(a: int) -> int:
    return a + 1


@anotation()
def abc1(a: int) -> float:
    return float(a + 1)


@anotation()
def abc2() -> float:
    return 1.0
