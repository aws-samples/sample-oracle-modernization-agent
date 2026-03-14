package amzn.bo.dto;

/**
 * 주문 취소 요청 DTO
 */
public class CancelOrderRequest {
    private String reason;
    
    public CancelOrderRequest() {}
    
    public CancelOrderRequest(String reason) {
        this.reason = reason;
    }
    
    public String getReason() {
        return reason;
    }
    
    public void setReason(String reason) {
        this.reason = reason;
    }
}
