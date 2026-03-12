package amzn.bo.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * AMZN 백오피스 주문 분석 DTO
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OrderAnalysisDto {
    
    private Long orderId;
    private String orderNumber;
    private Long userId;
    private String userEmail;
    private String userName;
    private String orderStatus;
    private BigDecimal totalAmount;
    private String currency;
    private String paymentMethod;
    
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime orderedAt;
    
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime shippedAt;
    
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime deliveredAt;
    
    // 주문 상세 분석 정보
    private Integer itemCount;
    private Integer uniqueProducts;
    private BigDecimal avgItemPrice;
    private BigDecimal discountPercentage;
    
    // 주문 처리 시간 분석
    private BigDecimal hoursToShip;
    private BigDecimal hoursToDeliver;
    
    // 고객 주문 패턴 분석
    private Long customerOrderCount;
    private BigDecimal customerTotalSpent;
    private BigDecimal customerAvgOrderValue;
    private Integer customerOrderSequence;
    
    // 주문 가치 분석
    private String orderValueCategory;
    
    // 계절성 분석
    private String orderQuarter;
    private String orderMonth;
    private String orderDayOfWeek;
}
