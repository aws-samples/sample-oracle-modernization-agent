package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
public class CustomerBehaviorDto {
    private Long userId;
    private String email;
    private LocalDateTime firstOrderDate;
    private LocalDateTime lastOrderDate;
    private Long totalOrders;
    private BigDecimal totalSpent;
    private BigDecimal avgOrderValue;
    private Long daysBetweenOrders;
    private String behaviorSegment;
    private BigDecimal loyaltyScore;
    private String riskLevel;
    private Long behaviorRank;
}
