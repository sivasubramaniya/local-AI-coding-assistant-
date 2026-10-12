# Java calculator sample — REAL model run

- Ollama 0.40.2, model `qwen2.5-coder-14b:latest` (REAL)
- Plan: `java-desktop-calculator`, 4 files: `src/calculator/Calculator.java`, `src/calculator/CalculatorApp.java`, `src/calculator/CalculatorTest.java`, `README.md`
- Generated into `%LOCALAPPDATA%\LocalAIAssistant\projects\java-desktop-calculator-2`: 4 written, failed: none
- Project check passed.
- Test commands (allowlisted): `javac -encoding UTF-8 -d out src/calculator/Calculator.java src/calculator/CalculatorApp.java src/calculator/CalculatorTest.java`; `java -cp out calculator.CalculatorTest`

## Checks initial run: PASSED (REAL javac/java)

`javac -encoding UTF-8 -d out src/calculator/Calculator.java src/calculator/CalculatorApp.java src/calculator/CalculatorTest.java` in `%LOCALAPPDATA%\LocalAIAssistant\projects\java-desktop-calculator-2`

Exit code 0 · 1.0 s

---

`java -cp out calculator.CalculatorTest` in `%LOCALAPPDATA%\LocalAIAssistant\projects\java-desktop-calculator-2`

Exit code 0 · 0.1 s

Output:
````text
PASS: add(2, 3) = 5
PASS: subtract(5, 3) = 2
PASS: multiply(4, 3) = 12
PASS: divide(10, 2) = 5
PASS: divide(10, 0) threw ArithmeticException with correct message
````

Total time: 9.0 min
