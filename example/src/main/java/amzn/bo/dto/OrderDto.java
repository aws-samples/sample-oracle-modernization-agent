package amzn.bo.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * AMZN 백오피스 주문 DTO
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OrderDto {
    
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
    
    // 검색 및 필터링용 필드들
    private String searchKeyword;
    private String statusFilter;
    private String paymentMethodFilter;
    private BigDecimal minAmount;
    private BigDecimal maxAmount;
    private String startDate;
    private String endDate;
    private String sortBy;
    private String sortDirection;
    private Integer page;
    private Integer size;
}
