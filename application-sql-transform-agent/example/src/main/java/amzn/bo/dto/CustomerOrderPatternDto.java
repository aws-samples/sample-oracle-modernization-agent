package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 고객 주문 패턴 분석 DTO
 */
@Data
public class CustomerOrderPatternDto {
    private Long userId;
    private String userName;
    private String userGrade;
    private Long totalOrders;
    private BigDecimal totalAmount;
    private BigDecimal avgOrderAmount;
    private String preferredPaymentMethod;
    private String mostOrderedCategory;
    private Integer daysBetweenOrders;
    private String orderFrequency;
    private LocalDateTime lastOrderDate;
    private LocalDateTime firstOrderDate;
    private String loyaltyScore;
}
