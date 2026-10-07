# Python Development Rules

General guidelines and best practices for Python development in the project. These rules are meant to ensure code quality, maintainability, and consistency across the codebase.

## Code Style

- Follow `flake8` guidelines for code formatting and style.
- Line length can be extended to 125 characters
- Use meaningful variable and function names that clearly indicate their purpose.
- Use consistent and short docstrings. If possible, keep one-line docstrings.
- In case of multiline docstrings, use Sphinx format
- Use type hints but don't fall into defining deep nested structures. If you need to define a complex type, consider using a dataclass or a named tuple instead.
- Use type hints with modern python way, e.g., `list[int]` instead of `List[int]` and `X | None` instead of `Optional[X]` etc.
- Import order: use `isort` with GOOGLE profile
- Functions and methods with 3 args can be linted in one line. Linting functions with more than 3 parameters should be formatted with following example (valid for definitions and calls):

```python
# BAD
def my_function(param1: int, param2: str, param3: float, param4: bool) -> None:
    ...

# GOOD
def my_function(
    param1: int,
    param2: str,
    param3: float,
    param4: bool
) -> None:
    ...

# GOOD (for functions with 3 or fewer parameters)
def my_function(param1: int, param2: str, param3: float) -> None:
    ...
```

- Use f-strings for string formatting instead of older methods like `%` or `str.format()`.
- Avoid using wildcard imports (e.g., `from module import *`)
- Avoid "magic numbers" and hardcoded values in the code. Use constants and define them at the first lines of the module.

## Coding principles

- SOLID is the way to go. Always strive to follow SOLID principles in your code design.
- DRY (Don't Repeat Yourself): Avoid code duplication
- Always keep in mind Zen of Python
- Avoid using global variables. If you need to share state, consider using classes or passing parameters explicitly.
- Use design patterns where appropriate, but don't over-engineer. The simplest solution that works is often the best.
- Separate the concerns
- Prefer composition over inheritance
- Keep components loosely coupled
- Design the code to be easy to test
- Use dependency injection to manage dependencies and improve testability.
- Never pass the exceptions without handling. Logging an error is a bare minimum.
- Avoid deep nesting of code. If you find yourself with multiple levels of indentation, consider refactoring into smaller functions or using guard clauses.
- Fail fast rule.
- Readability counts. Always prioritize readability and maintainability over cleverness or micro-optimizations.
- List and dict comprehensions are nice but don't overuse them
- Use Model, controller, view pattern for API design
- When Singleton is needed, just use a module with functions and state instead of implementing a Singleton

## Python Project setup

- Use virtual environments to manage dependencies and isolate project environments.
- virtual environment directory `.venv`
- Use pip for package management and requirements.txt for listing dependencies.
- dependencies should be listed with fixed version
- main package should be named as project

# Python Codebase Tests Design

## Tech Stack

- Pytest
- Mock and MagicMock for mocking dependencies

## Tests Style

- Tests should be organized in a separate `tests/` directory at the root of the project.
- Test files should be named with the `test_` prefix, e.g., `test_module.py`.
- Test functions should also be named with the `test_` prefix, e.g., `test_functionality()`.
- Use fixtures  set up and teardown any necessary test data or state.
- Unit Tests should be independent and not rely on the state of other tests. Each test should be able to run in isolation. Order of the tests should not matter.
- Tests naming conventions: descriptive names for test functions functionality they are testing or direct function or method it is testing.
- Each test should cover single requirement or functionality
- Use parameterized tests to cover multiple scenarios with different inputs and expected outcomes.
- For unit tests, structure of the tests folder should mirror the structure of the source code
- Use assertions to verify the expected outcomes of tests
- Structure of a test should follow the Conditions-Action-Expectations pattern:
- Use conftest.py file to define fixtures and any common setup or teardown logic which need to be shared across multiple test files.
- Test cases should be designed with a `conditions`, `action`, and `expectations`.
- If some tests are already in place, they should be used as a reference for the design and structure of new tests.
- If there is a lot of parameterization in a test, define a parameterization list as a separate constant with a meaningful name

  ```python
  TEST_CASES = [
      # input, expected_output
      (input1, expected_output1),
      (input2, expected_output2),
      # ...
  ]

  @pytest.mark.parametrize("input, expected_output", TEST_CASES)
  def test_functionality(input, expected_output):
      # test implementation
  ```

## Caveats

- Tests should be designed to be maintainable and easy to understand.
- Tests should be designed to provide clear feedback
- Tests Should not be flaky
- Do not test implementation details, but rather the expected behavior of the code under test.
- 100% code coverage is not a "must have" goal. Avoid creating a tests which only exist to increase code coverage without providing meaningful validation of the code's behavior.
- Some tests are not worth writing. If it is not possible to test function without mocking everything it is better to mark this test to skip. Example:

```python
# BAD EXAMPLES
def test_get_function():
    # Conditions
    test_get_function = mock.Mock(return_value=42)  # Mocking function under test - NO SENSE

    # Action
    actual = test_get_function("spam")  # Action contain only mocked function call - NO SENSE

    # Expectations
    assert test_get_function.called_once()  # This is not testing anything, because we are calling mocked function directly in action
    assert actual == 42  #  Verifying that mocked function returns expected value which was defined in test setup - NO SENSE

# GOOD EXAMPLE
@pytest.mark.skip(reason="Not testable in unit tests. Direct API call. Tested in Integration tests")
def test_functionality():
    pass
```

- Tests which are verifying only if tested function is called does not test anything in fact.
- If test is not passing maybe the implementation is wrong, not the test! Consider if the test is correct before changing it to make it pass!
- Don't create a tests which are testing 3rd party libraries. For example, if You are using a database API, dot test direct call of API to verify if data is in a database with the same API. Instead, test the functionality of your code which is using the database API, and mock the database API calls to verify that they are being called with the expected parameters. This way you are testing your code's behavior and not the behavior of the 3rd party library.
- If Test are to complex or complicated maybe the implementation is too complex and should be refactored to be more testable. Consider if the implementation can be simplified or broken down into smaller, more manageable pieces.
- If there is too many mocking in a test, maybe the code under test is too tightly coupled to its dependencies. Maybe implementation is wrong or maybe there is no other way than integration or system test.
