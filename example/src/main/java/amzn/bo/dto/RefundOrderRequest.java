package amzn.bo.dto;

import java.math.BigDecimal;

/**
 * 주문 환불 요청 DTO
 */
public class RefundOrderRequest {
    private String reason;
    private BigDecimal amount;  // 환불 금액 (부분 환불 지원)
    private String refundType;  // FULL, PARTIAL
    
    public RefundOrderRequest() {}
    
    public RefundOrderRequest(String reason, BigDecimal amount, String refundType) {
        this.reason = reason;
        this.amount = amount;
        this.refundType = refundType;
    }
    
    public String getReason() {
        return reason;
    }
    
    public void setReason(String reason) {
        this.reason = reason;
    }
    
    public BigDecimal getAmount() {
        return amount;
    }
    
    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
    
    public String getRefundType() {
        return refundType;
    }
    
    public void setRefundType(String refundType) {
        this.refundType = refundType;
    }
}
