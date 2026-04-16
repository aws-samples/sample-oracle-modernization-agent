package com.kns.framework.util;

/**
 * Stub for MyBatis OGNL expressions.
 * Only notEmpty/empty are needed for test execution.
 */
public class CmFunction {

    public static boolean notEmpty(Object value) {
        if (value == null) return false;
        if (value instanceof String) return !((String) value).trim().isEmpty();
        return true;
    }

    public static boolean empty(Object value) {
        return !notEmpty(value);
    }
}
