package calculator;

import javax.swing.*;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.awt.event.ActionListener;

public class CalculatorApp extends JFrame {

    private JTextField inputField1;
    private JTextField inputField2;
    private JLabel resultLabel;
    private Calculator calculator;

    public CalculatorApp() {
        calculator = new Calculator();
        setTitle("Calculator");
        setSize(300, 200);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        setLocationRelativeTo(null);
        setLayout(new GridLayout(4, 2));

        inputField1 = new JTextField();
        inputField2 = new JTextField();
        resultLabel = new JLabel("Result: ");

        add(new JLabel("Number 1:"));
        add(inputField1);
        add(new JLabel("Number 2:"));
        add(inputField2);
        add(new JLabel("Operation:"));
        add(resultLabel);

        JButton addButton = new JButton("Add");
        addButton.addActionListener(new OperationListener("add"));
        add(addButton);

        JButton subtractButton = new JButton("Subtract");
        subtractButton.addActionListener(new OperationListener("subtract"));
        add(subtractButton);

        JButton multiplyButton = new JButton("Multiply");
        multiplyButton.addActionListener(new OperationListener("multiply"));
        add(multiplyButton);

        JButton divideButton = new JButton("Divide");
        divideButton.addActionListener(new OperationListener("divide"));
        add(divideButton);
    }

    private class OperationListener implements ActionListener {
        private String operation;

        public OperationListener(String operation) {
            this.operation = operation;
        }

        @Override
        public void actionPerformed(ActionEvent e) {
            try {
                double num1 = Double.parseDouble(inputField1.getText());
                double num2 = Double.parseDouble(inputField2.getText());
                double result = 0;

                switch (operation) {
                    case "add":
                        result = calculator.add(num1, num2);
                        break;
                    case "subtract":
                        result = calculator.subtract(num1, num2);
                        break;
                    case "multiply":
                        result = calculator.multiply(num1, num2);
                        break;
                    case "divide":
                        result = calculator.divide(num1, num2);
                        break;
                }

                resultLabel.setText("Result: " + result);
            } catch (NumberFormatException ex) {
                resultLabel.setText("Result: Invalid input");
            } catch (ArithmeticException ex) {
                resultLabel.setText("Result: " + ex.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            CalculatorApp app = new CalculatorApp();
            app.setVisible(true);
        });
    }
}
