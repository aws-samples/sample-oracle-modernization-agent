package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
public class UserBehaviorPatternDto {
    private Long userId;
    private String email;
    private String status;
    private LocalDateTime createdAt;
    private LocalDateTime lastOrderDate;
    private Long totalOrders;
    private BigDecimal totalSpent;
    private BigDecimal avgOrderValue;
    private Long daysSinceLastOrder;
    private String activityLevel;
    private Long activityRank;
    private BigDecimal activityScore;
}
