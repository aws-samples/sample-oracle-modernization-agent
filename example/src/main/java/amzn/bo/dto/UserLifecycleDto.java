package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
public class UserLifecycleDto {
    private Long userId;
    private String email;
    private String status;
    private LocalDateTime createdAt;
    private Long daysSinceRegistration;
    private LocalDateTime firstOrderDate;
    private LocalDateTime lastOrderDate;
    private Long totalOrders;
    private BigDecimal totalSpent;
    private Long daysSinceLastOrder;
    private String lifecycleStage;
    private BigDecimal activityScore;
    private String riskLevel;
}
