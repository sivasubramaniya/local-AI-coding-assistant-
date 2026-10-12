package calculator;

public class CalculatorTest {

    public static void main(String[] args) {
        Calculator calculator = new Calculator();

        // Test add method
        if (calculator.add(2, 3) == 5) {
            System.out.println("PASS: add(2, 3) = 5");
        } else {
            System.out.println("FAIL: add(2, 3) != 5");
            System.exit(1);
        }

        // Test subtract method
        if (calculator.subtract(5, 3) == 2) {
            System.out.println("PASS: subtract(5, 3) = 2");
        } else {
            System.out.println("FAIL: subtract(5, 3) != 2");
            System.exit(1);
        }

        // Test multiply method
        if (calculator.multiply(4, 3) == 12) {
            System.out.println("PASS: multiply(4, 3) = 12");
        } else {
            System.out.println("FAIL: multiply(4, 3) != 12");
            System.exit(1);
        }

        // Test divide method
        if (calculator.divide(10, 2) == 5) {
            System.out.println("PASS: divide(10, 2) = 5");
        } else {
            System.out.println("FAIL: divide(10, 2) != 5");
            System.exit(1);
        }

        // Test divide by zero exception
        try {
            calculator.divide(10, 0);
            System.out.println("FAIL: divide(10, 0) did not throw ArithmeticException");
            System.exit(1);
        } catch (ArithmeticException e) {
            if (e.getMessage().equals("Division by zero")) {
                System.out.println("PASS: divide(10, 0) threw ArithmeticException with correct message");
            } else {
                System.out.println("FAIL: divide(10, 0) threw ArithmeticException with incorrect message");
                System.exit(1);
            }
        }
    }
}
