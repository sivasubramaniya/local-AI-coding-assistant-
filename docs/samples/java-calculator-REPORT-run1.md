# Java calculator sample — REAL model run

- Ollama 0.40.2, model `qwen2.5-coder-14b:latest` (REAL)
- Plan: `java-desktop-calculator`, 4 files: `src/calculator/Calculator.java`, `src/calculator/CalculatorApp.java`, `src/calculator/CalculatorTest.java`, `README.md`
- Generated into `%LOCALAPPDATA%\LocalAIAssistant\projects\java-desktop-calculator`: 3 written, failed: {'README.md': 'The file was cut off. (unclosed code fence)'}
- Project check: no README file.
- Test commands (allowlisted): `javac -encoding UTF-8 -d out src/calculator/Calculator.java src/calculator/CalculatorApp.java src/calculator/CalculatorTest.java`

## Checks initial run: FAILED (REAL javac/java)

`javac -encoding UTF-8 -d out src/calculator/Calculator.java src/calculator/CalculatorApp.java src/calculator/CalculatorTest.java` in `%LOCALAPPDATA%\LocalAIAssistant\projects\java-desktop-calculator`

Exit code 1 · 1.0 s

Errors:
````text
src\calculator\CalculatorTest.java:3: error: package org.junit.jupiter.api does not exist
import org.junit.jupiter.api.Test;
                            ^
src\calculator\CalculatorTest.java:4: error: package org.junit.jupiter.api does not exist
import static org.junit.jupiter.api.Assertions.*;
                                   ^
src\calculator\CalculatorTest.java:8: error: cannot find symbol
    @Test
     ^
  symbol:   class Test
  location: class CalculatorTest
src\calculator\CalculatorTest.java:14: error: cannot find symbol
    @Test
     ^
  symbol:   class Test
  location: class CalculatorTest
src\calculator\CalculatorTest.java:20: error: cannot find symbol
    @Test
     ^
  symbol:   class Test
  location: class CalculatorTest
src\calculator\CalculatorTest.java:26: error: cannot find symbol
    @Test
     ^
  symbol:   class Test
  location: class CalculatorTest
src\calculator\CalculatorTest.java:32: error: cannot find symbol
    @Test
     ^
  symbol:   class Test
  location: class CalculatorTest
src\calculator\CalculatorApp.java:55: error: cannot find symbol
                calculator.clear();
                          ^
  symbol:   method clear()
  location: variable calculator of type Calculator
src\calculator\CalculatorApp.java:58: error: cannot find symbol
                    double result = calculator.calculate(display.getText());
                                              ^
  symbol:   method calculate(String)
  location: variable calculator of type Calculator
src\calculator\CalculatorApp.java:64: error: cannot find symbol
                calculator.setOperation(command);
                          ^
  symbol:   method setOperation(String)
  location: variable calculator of type Calculator
src\calculator\CalculatorApp.java:65: error: cannot find symbol
                calculator.setOperand(display.getText());
                          ^
  symbol:   method setOperand(String)
  location: variable calculator of type Calculator
src\calculator\CalculatorTest.java:11: error: cannot find symbol
        assertEquals(5, calculator.add(2, 3));
        ^
  symbol:   method assertEquals(int,double)
  location: class CalculatorTest
src\calculator\CalculatorTest.java:17: error: cannot find symbol
        assertEquals(1, calculator.subtract(4, 3));
        ^
  symbol:   method assertEquals(int,double)
  location: class CalculatorTest
src\calculator\CalculatorTest.java:23: error: cannot find symbol
        assertEquals(6, calculator.multiply(2, 3));
        ^
  symbol:   method assertEquals(int,double)
  location: class CalculatorTest
src\calculator\CalculatorTest.java:29: error: cannot find symbol
        assertEquals(2, calculator.divide(6, 3));
        ^
  symbol:   method assertEquals(int,double)
  location: class CalculatorTest
src\calculator\CalculatorTest.java:35: error: cannot find symbol
        Exception exception = assertThrows(ArithmeticException.class, () -> {
                              ^
  symbol:   method assertThrows(Class<ArithmeticException>,()->{ calc[...]0); })
  location: class CalculatorTest
src\calculator\CalculatorTest.java:38: error: cannot find symbol
        assertEquals("Cannot divide by zero", exception.getMessage());
        ^
  symbol:   method assertEquals(String,String)
  location: class CalculatorTest
17 errors
````
- Repair round 1: model proposed 0 file change(s)
- Repair stopped: no usable fix was proposed.

Total time: 10.5 min
