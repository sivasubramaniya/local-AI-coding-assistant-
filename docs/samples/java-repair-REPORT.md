# Java repair demo — REAL model run

- Ollama 0.40.2, model `qwen2.5-coder-14b:latest` (REAL)
- Copied the generated sample to `%LOCALAPPDATA%\LocalAIAssistant\projects\java-calculator-repair-demo` and injected a bug: `a + b` -> `a - b` in Calculator.add (MOCK bug, REAL repair)
- Test commands (allowlisted): `javac -encoding UTF-8 -d out src/calculator/Calculator.java src/calculator/CalculatorApp.java src/calculator/CalculatorTest.java`; `java -cp out calculator.CalculatorTest`

## Checks initial run: FAILED (REAL javac/java)

`javac -encoding UTF-8 -d out src/calculator/Calculator.java src/calculator/CalculatorApp.java src/calculator/CalculatorTest.java` in `%LOCALAPPDATA%\LocalAIAssistant\projects\java-calculator-repair-demo`

Exit code 0 · 0.8 s

---

`java -cp out calculator.CalculatorTest` in `%LOCALAPPDATA%\LocalAIAssistant\projects\java-calculator-repair-demo`

Exit code 1 · 0.1 s

Output:
````text
FAIL: add(2, 3) != 5
````
- Repair round 1: model proposed 1 file change(s)

```diff
--- a/src/calculator/Calculator.java
+++ b/src/calculator/Calculator.java
@@ -3,7 +3,7 @@
 public class Calculator {
 
     public double add(double a, double b) {
-        return a - b;
+        return a + b; // Fixed the addition operation
     }
 
     public double subtract(double a, double b) {
```
- Applied (with .bak backups): src/calculator/Calculator.java

## Checks after repair round 1: PASSED (REAL javac/java)

`javac -encoding UTF-8 -d out src/calculator/Calculator.java src/calculator/CalculatorApp.java src/calculator/CalculatorTest.java` in `%LOCALAPPDATA%\LocalAIAssistant\projects\java-calculator-repair-demo`

Exit code 0 · 0.8 s

---

`java -cp out calculator.CalculatorTest` in `%LOCALAPPDATA%\LocalAIAssistant\projects\java-calculator-repair-demo`

Exit code 0 · 0.1 s

Output:
````text
PASS: add(2, 3) = 5

PASS: subtract(5, 3) = 2

PASS: multiply(4, 3) = 12

PASS: divide(10, 2) = 5

PASS: divide(10, 0) threw ArithmeticException with correct message
````

Total time: 1.7 min
