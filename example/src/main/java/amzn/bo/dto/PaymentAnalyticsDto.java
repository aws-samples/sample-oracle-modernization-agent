package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

@Data
public class PaymentAnalyticsDto {
    private String paymentMethod;
    private String paymentStatus;
    private String country;
    private Long transactionCount;
    private BigDecimal totalAmount;
    private BigDecimal avgTransactionAmount;
    private BigDecimal successRate;
    private BigDecimal failureRate;
    private Integer methodGrouping;
    private Integer statusGrouping;
    private Integer countryGrouping;
}
