package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

@Data
public class PaymentFailurePatternDto {
    private String paymentMethod;
    private String failureReason;
    private String country;
    private Long failureCount;
    private BigDecimal failureRate;
    private Long totalTransactions;
    private BigDecimal avgFailureAmount;
    private Long rank;
}
