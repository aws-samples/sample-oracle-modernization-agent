package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

/**
 * 주문 처리 시간 분석 DTO
 */
@Data
public class OrderProcessingTimeDto {
    private String orderStatus;
    private String paymentMethod;
    private String shippingCountry;
    private Long orderCount;
    private BigDecimal avgProcessingHours;
    private BigDecimal minProcessingHours;
    private BigDecimal maxProcessingHours;
    private BigDecimal medianProcessingHours;
    private BigDecimal stddevProcessingHours;
}
