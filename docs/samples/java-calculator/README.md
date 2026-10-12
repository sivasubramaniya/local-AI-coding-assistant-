# Java Desktop Calculator

## Build Instructions

To build the project, navigate to the root directory of the project and run the following command:

```sh
javac -d bin src/calculator/*.java
```

This command compiles the Java source files and places the compiled classes in the `bin` directory.

## Run Instructions

To run the calculator application, use the following command:

```sh
java -cp bin calculator.CalculatorApp
```

This command starts the Swing-based calculator application.

## Test Instructions

To run the tests, use the following command:

```sh
java -cp bin calculator.CalculatorTest
```

This command runs the plain test class `CalculatorTest` which checks the basic arithmetic operations and the division-by-zero exception handling. The test results will be printed to the console.
