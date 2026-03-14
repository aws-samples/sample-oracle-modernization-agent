package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
public class DormantUserDto {
    private Long userId;
    private String email;
    private String status;
    private LocalDateTime createdAt;
    private LocalDateTime lastOrderDate;
    private Long daysSinceLastOrder;
    private Long totalOrders;
    private BigDecimal totalSpent;
    private BigDecimal avgOrderValue;
    private String favoriteCategory;
    private String favoriteCategoryName;
    private BigDecimal reactivationProbability;
    private Long reactivationPriority;
    private String recommendedAction;
}
