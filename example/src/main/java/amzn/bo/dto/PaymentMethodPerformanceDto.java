package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

@Data
public class PaymentMethodPerformanceDto {
    private String paymentMethod;
    private Long totalTransactions;
    private Long successfulTransactions;
    private Long failedTransactions;
    private BigDecimal totalAmount;
    private BigDecimal successfulAmount;
    private BigDecimal avgTransactionAmount;
    private BigDecimal successRate;
    private BigDecimal failureRate;
    private BigDecimal avgProcessingTimeMinutes;
    private String performanceGrade;
    private BigDecimal morningUsageRate;
    private BigDecimal afternoonUsageRate;
    private BigDecimal eveningUsageRate;
    private BigDecimal nightUsageRate;
    private String preferredTimeSlot;
    private Long overallRank;
}
