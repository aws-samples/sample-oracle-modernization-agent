package com.kns.framework.util;

/**
 * Stub for MyBatis OGNL expressions.
 * Only isEmpty/isNotEmpty are needed for test execution.
 */
public class StringUtil {

    public static boolean isEmpty(Object value) {
        if (value == null) return true;
        if (value instanceof String) return ((String) value).trim().isEmpty();
        return false;
    }

    public static boolean isNotEmpty(Object value) {
        return !isEmpty(value);
    }
}
