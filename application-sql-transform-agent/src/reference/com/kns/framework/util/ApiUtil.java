package com.kns.framework.util;

import java.util.Collection;
import java.util.Map;

/**
 * Stub for MyBatis OGNL expressions.
 * Only notEmpty/empty are needed for test execution.
 */
public class ApiUtil {

    public static boolean notEmpty(Object value) {
        if (value == null) return false;
        if (value instanceof String) return !((String) value).trim().isEmpty();
        if (value instanceof Collection) return !((Collection<?>) value).isEmpty();
        if (value instanceof Map) return !((Map<?, ?>) value).isEmpty();
        if (value.getClass().isArray()) return java.lang.reflect.Array.getLength(value) > 0;
        return true;
    }

    public static boolean empty(Object value) {
        return !notEmpty(value);
    }
}
